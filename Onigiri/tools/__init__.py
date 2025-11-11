# Onigiri Tools Module
# Collection of specialized tools for the Onigiri Blender add-on

from . import sl_slice_exporter

def register():
    sl_slice_exporter.register()

def unregister():
    sl_slice_exporter.unregister()
