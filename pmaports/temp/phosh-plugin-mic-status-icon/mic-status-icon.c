/*
 * Microphone status icon for phosh: shown while an application records
 * audio, like phosh's camera status icon (0.59) and GNOME Shell's
 * microphone indicator. Built out of tree against phosh's status-icon.h;
 * the symbols resolve from the running phosh.
 *
 * Recording streams are PulseAudio source outputs, as in GNOME Shell (which
 * gets them through libgvc). That covers PulseAudio (postmarketOS' phosh
 * still uses it; PipeWire only carries video there) and pipewire-pulse,
 * which lists native PipeWire capture streams as source outputs as well.
 *
 * Based on phosh's camera-status-icon plugin and camera-manager,
 * Copyright (C) 2026 Phosh.mobi e.V.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#define G_LOG_DOMAIN "phosh-plugin-mic-status-icon"

#include "status-icon.h"

#include <gio/gio.h>
#include <pulse/glib-mainloop.h>
#include <pulse/pulseaudio.h>

#define PLUGIN_NAME "mic-status-icon"
/* From phosh's plugins/meson.build (phosh-plugin.h is generated there) */
#define PHOSH_PLUGIN_EXTENSION_POINT_STATUS_ICON_WIDGET "phosh-status-icon-widget"

#define RECONNECT_DELAY_S 2
/* Coalesce bursts of stream events into one query */
#define REFRESH_DELAY_MS 100
/* Avoid flicker when an app re-creates its stream */
#define DISABLE_DELAY_MS 500

#define PHOSH_TYPE_MIC_STATUS_ICON (phosh_mic_status_icon_get_type ())
G_DECLARE_FINAL_TYPE (PhoshMicStatusIcon, phosh_mic_status_icon, PHOSH, MIC_STATUS_ICON,
                      PhoshStatusIcon)

enum {
  PROP_0,
  PROP_IN_USE,
  PROP_LAST_PROP
};
static GParamSpec *props[PROP_LAST_PROP];

struct _PhoshMicStatusIcon {
  PhoshStatusIcon   parent;

  pa_glib_mainloop *mainloop;
  pa_context       *context;
  GHashTable       *monitors;     /* indices of sources that monitor a sink */
  gboolean          recording;    /* result of the query in progress */
  gboolean          querying;
  gboolean          query_again;  /* events arrived during the query */
  guint             refresh_id;
  guint             reconnect_id;
  guint             disable_id;
  GBinding         *binding;

  gboolean          in_use;
};

G_DEFINE_TYPE (PhoshMicStatusIcon, phosh_mic_status_icon, PHOSH_TYPE_STATUS_ICON)

static void connect_pulse (PhoshMicStatusIcon *self);
static void query (PhoshMicStatusIcon *self);


static void
set_in_use (PhoshMicStatusIcon *self, gboolean in_use)
{
  if (self->in_use == in_use)
    return;

  g_debug ("Microphone in use: %d", in_use);
  self->in_use = in_use;
  g_object_notify_by_pspec (G_OBJECT (self), props[PROP_IN_USE]);
}


static void
on_disable (gpointer data)
{
  PhoshMicStatusIcon *self = PHOSH_MIC_STATUS_ICON (data);

  self->disable_id = 0;
  set_in_use (self, FALSE);
}


static void
update_in_use (PhoshMicStatusIcon *self, gboolean in_use)
{
  if (in_use) {
    g_clear_handle_id (&self->disable_id, g_source_remove);
    set_in_use (self, TRUE);
  } else if (self->in_use && self->disable_id == 0) {
    self->disable_id = g_timeout_add_once (DISABLE_DELAY_MS, on_disable, self);
  }
}


/*
 * A recording application: a running source output that does not record
 * an output's monitor (what is played rather than the microphone) and is
 * not a level meter (pavucontrol's and GNOME Settings' peak detection).
 */
static gboolean
is_recording (PhoshMicStatusIcon *self, const pa_source_output_info *info)
{
  const char *media_name, *app_id;

  if (info->corked)
    return FALSE;

  if (g_hash_table_contains (self->monitors, GUINT_TO_POINTER (info->source)))
    return FALSE;

  media_name = pa_proplist_gets (info->proplist, PA_PROP_MEDIA_NAME);
  if (g_strcmp0 (media_name, "Peak detect") == 0)
    return FALSE;

  /* The volume controls GNOME Shell ignores, too */
  app_id = pa_proplist_gets (info->proplist, PA_PROP_APPLICATION_ID);
  if (g_strcmp0 (app_id, "org.gnome.VolumeControl") == 0 ||
      g_strcmp0 (app_id, "org.PulseAudio.pavucontrol") == 0)
    return FALSE;

  return TRUE;
}


static void
on_source_output_info (pa_context                  *context,
                       const pa_source_output_info *info,
                       int                          eol,
                       void                        *data)
{
  PhoshMicStatusIcon *self = PHOSH_MIC_STATUS_ICON (data);

  if (eol) {
    self->querying = FALSE;
    update_in_use (self, self->recording);
    if (self->query_again)
      query (self);
    return;
  }

  if (is_recording (self, info)) {
    g_debug ("Recording: source output %u (%s)", info->index,
             pa_proplist_gets (info->proplist, PA_PROP_APPLICATION_NAME) ?: "unknown");
    self->recording = TRUE;
  }
}


static void
on_source_info (pa_context *context, const pa_source_info *info, int eol, void *data)
{
  PhoshMicStatusIcon *self = PHOSH_MIC_STATUS_ICON (data);
  pa_operation *op;

  if (!eol) {
    if (info->monitor_of_sink != PA_INVALID_INDEX)
      g_hash_table_add (self->monitors, GUINT_TO_POINTER (info->index));
    return;
  }

  op = pa_context_get_source_output_info_list (context, on_source_output_info, self);
  if (op)
    pa_operation_unref (op);
  else
    self->querying = FALSE;
}


/* Sources first (to know the monitors), then the source outputs */
static void
query (PhoshMicStatusIcon *self)
{
  pa_operation *op;

  if (self->context == NULL || pa_context_get_state (self->context) != PA_CONTEXT_READY)
    return;

  if (self->querying) {
    self->query_again = TRUE;
    return;
  }

  self->querying = TRUE;
  self->query_again = FALSE;
  self->recording = FALSE;
  g_hash_table_remove_all (self->monitors);

  op = pa_context_get_source_info_list (self->context, on_source_info, self);
  if (op)
    pa_operation_unref (op);
  else
    self->querying = FALSE;
}


static void
on_refresh (gpointer data)
{
  PhoshMicStatusIcon *self = PHOSH_MIC_STATUS_ICON (data);

  self->refresh_id = 0;
  query (self);
}


static void
on_subscribe_event (pa_context *context, pa_subscription_event_type_t type, uint32_t index,
                    void *data)
{
  PhoshMicStatusIcon *self = PHOSH_MIC_STATUS_ICON (data);

  if (self->refresh_id == 0)
    self->refresh_id = g_timeout_add_once (REFRESH_DELAY_MS, on_refresh, self);
}


static void
disconnect_pulse (PhoshMicStatusIcon *self)
{
  g_clear_handle_id (&self->refresh_id, g_source_remove);
  g_clear_handle_id (&self->disable_id, g_source_remove);
  self->querying = FALSE;

  if (self->context) {
    pa_context_set_state_callback (self->context, NULL, NULL);
    pa_context_set_subscribe_callback (self->context, NULL, NULL);
    pa_context_disconnect (self->context);
    g_clear_pointer (&self->context, pa_context_unref);
  }

  /* Without a sound server we can't know, don't wait */
  set_in_use (self, FALSE);
}


static gboolean
on_reconnect (gpointer data)
{
  PhoshMicStatusIcon *self = PHOSH_MIC_STATUS_ICON (data);

  self->reconnect_id = 0;
  connect_pulse (self);

  return G_SOURCE_REMOVE;
}


static void
on_context_state (pa_context *context, void *data)
{
  PhoshMicStatusIcon *self = PHOSH_MIC_STATUS_ICON (data);
  pa_operation *op;

  switch (pa_context_get_state (context)) {
  case PA_CONTEXT_READY:
    g_debug ("Connected to the sound server");
    pa_context_set_subscribe_callback (context, on_subscribe_event, self);
    op = pa_context_subscribe (context,
                               PA_SUBSCRIPTION_MASK_SOURCE | PA_SUBSCRIPTION_MASK_SOURCE_OUTPUT,
                               NULL, NULL);
    if (op)
      pa_operation_unref (op);
    query (self);
    break;
  case PA_CONTEXT_FAILED:
  case PA_CONTEXT_TERMINATED:
    /* The sound server is a user service that can restart: keep trying */
    g_debug ("Lost the sound server: %s", pa_strerror (pa_context_errno (context)));
    disconnect_pulse (self);
    if (self->reconnect_id == 0)
      self->reconnect_id = g_timeout_add_seconds (RECONNECT_DELAY_S, on_reconnect, self);
    break;
  case PA_CONTEXT_UNCONNECTED:
  case PA_CONTEXT_CONNECTING:
  case PA_CONTEXT_AUTHORIZING:
  case PA_CONTEXT_SETTING_NAME:
  default:
    break;
  }
}


static void
connect_pulse (PhoshMicStatusIcon *self)
{
  pa_proplist *proplist;

  proplist = pa_proplist_new ();
  pa_proplist_sets (proplist, PA_PROP_APPLICATION_NAME, "Phosh microphone indicator");
  pa_proplist_sets (proplist, PA_PROP_APPLICATION_ID, "mobi.phosh.MicStatusIcon");
  self->context = pa_context_new_with_proplist (pa_glib_mainloop_get_api (self->mainloop),
                                                NULL, proplist);
  pa_proplist_free (proplist);
  if (self->context == NULL) {
    g_warning ("Failed to create a PulseAudio context");
    return;
  }

  pa_context_set_state_callback (self->context, on_context_state, self);
  /* NOFAIL: wait for a sound server that is not up yet */
  if (pa_context_connect (self->context, NULL, PA_CONTEXT_NOFAIL, NULL) < 0)
    g_warning ("Failed to connect to the sound server: %s",
               pa_strerror (pa_context_errno (self->context)));
}


static void
unbind (PhoshMicStatusIcon *self)
{
  GBinding *binding = self->binding;

  /* The weak pointer clears it if the revealer went away first */
  if (binding == NULL)
    return;

  g_object_remove_weak_pointer (G_OBJECT (binding), (gpointer *)&self->binding);
  self->binding = NULL;
  g_binding_unbind (binding);
}


static void
phosh_mic_status_icon_realize (GtkWidget *widget)
{
  PhoshMicStatusIcon *self = PHOSH_MIC_STATUS_ICON (widget);
  GtkWidget *gtkrevealer, *phoshrevealer;

  GTK_WIDGET_CLASS (phosh_mic_status_icon_parent_class)->realize (widget);

  /*
   * As the camera icon: hide completely while the microphone is unused by
   * driving the PhoshRevealer the status icons box wraps us in.
   */
  gtkrevealer = gtk_widget_get_parent (widget);
  phoshrevealer = gtkrevealer ? gtk_widget_get_parent (gtkrevealer) : NULL;
  if (phoshrevealer == NULL ||
      g_object_class_find_property (G_OBJECT_GET_CLASS (phoshrevealer), "show-child") == NULL) {
    g_warning ("Not inside a PhoshRevealer, can't hide");
    return;
  }

  unbind (self);
  self->binding = g_object_bind_property (self, "in-use", phoshrevealer, "show-child",
                                          G_BINDING_SYNC_CREATE);
  g_object_add_weak_pointer (G_OBJECT (self->binding), (gpointer *)&self->binding);
}


static void
phosh_mic_status_icon_get_property (GObject    *object,
                                    guint       property_id,
                                    GValue     *value,
                                    GParamSpec *pspec)
{
  PhoshMicStatusIcon *self = PHOSH_MIC_STATUS_ICON (object);

  switch (property_id) {
  case PROP_IN_USE:
    g_value_set_boolean (value, self->in_use);
    break;
  default:
    G_OBJECT_WARN_INVALID_PROPERTY_ID (object, property_id, pspec);
    break;
  }
}


static void
phosh_mic_status_icon_dispose (GObject *object)
{
  PhoshMicStatusIcon *self = PHOSH_MIC_STATUS_ICON (object);

  unbind (self);
  g_clear_handle_id (&self->reconnect_id, g_source_remove);
  disconnect_pulse (self);
  g_clear_pointer (&self->mainloop, pa_glib_mainloop_free);

  G_OBJECT_CLASS (phosh_mic_status_icon_parent_class)->dispose (object);
}


static void
phosh_mic_status_icon_finalize (GObject *object)
{
  PhoshMicStatusIcon *self = PHOSH_MIC_STATUS_ICON (object);

  g_clear_pointer (&self->monitors, g_hash_table_unref);

  G_OBJECT_CLASS (phosh_mic_status_icon_parent_class)->finalize (object);
}


static void
phosh_mic_status_icon_class_init (PhoshMicStatusIconClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);
  GtkWidgetClass *widget_class = GTK_WIDGET_CLASS (klass);

  object_class->get_property = phosh_mic_status_icon_get_property;
  object_class->dispose = phosh_mic_status_icon_dispose;
  object_class->finalize = phosh_mic_status_icon_finalize;

  widget_class->realize = phosh_mic_status_icon_realize;

  /**
   * PhoshMicStatusIcon:in-use:
   *
   * Whether an application is recording audio.
   */
  props[PROP_IN_USE] =
    g_param_spec_boolean ("in-use", "", "",
                          FALSE,
                          G_PARAM_READABLE | G_PARAM_STATIC_STRINGS | G_PARAM_EXPLICIT_NOTIFY);

  g_object_class_install_properties (object_class, PROP_LAST_PROP, props);
}


static void
phosh_mic_status_icon_init (PhoshMicStatusIcon *self)
{
  g_object_set (self,
                "icon-name", "audio-input-microphone-symbolic",
                "pixel-size", 16,
                NULL);
  gtk_style_context_add_class (gtk_widget_get_style_context (GTK_WIDGET (self)),
                               "p-privacy-indicator");
  atk_object_set_name (gtk_widget_get_accessible (GTK_WIDGET (self)), "Microphone Indicator");

  self->monitors = g_hash_table_new (g_direct_hash, g_direct_equal);
  self->mainloop = pa_glib_mainloop_new (NULL);
  connect_pulse (self);
}


G_MODULE_EXPORT char **g_io_phosh_plugin_mic_status_icon_query (void);
G_MODULE_EXPORT void g_io_module_load (GIOModule *module);
G_MODULE_EXPORT void g_io_module_unload (GIOModule *module);


void
g_io_module_load (GIOModule *module)
{
  g_type_module_use (G_TYPE_MODULE (module));

  g_io_extension_point_implement (PHOSH_PLUGIN_EXTENSION_POINT_STATUS_ICON_WIDGET,
                                  PHOSH_TYPE_MIC_STATUS_ICON,
                                  PLUGIN_NAME,
                                  10);
}


void
g_io_module_unload (GIOModule *module)
{
}


char **
g_io_phosh_plugin_mic_status_icon_query (void)
{
  char *extension_points[] = {PHOSH_PLUGIN_EXTENSION_POINT_STATUS_ICON_WIDGET, NULL};

  return g_strdupv (extension_points);
}
