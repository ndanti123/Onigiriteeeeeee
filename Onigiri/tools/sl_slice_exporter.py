# Onigiri/tools/sl_slice_exporter.py
# Blender add-on module to batch export SL .anim files in sliding/overlapping windows.

import bpy
import os
from math import ceil

try:
    from Onigiri import animutils
except Exception:
    animutils = None

from bpy.props import (
    StringProperty,
    BoolProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
)


class OniSLSliceSettings(bpy.types.PropertyGroup):
    output_dir: StringProperty(
        name="Output Folder",
        subtype='DIR_PATH',
        default="//"
    )
    file_prefix: StringProperty(
        name="File Prefix",
        default="anim"
    )
    window_seconds: FloatProperty(
        name="Window (seconds)",
        default=30.0,
        min=0.1
    )
    step_seconds: FloatProperty(
        name="Step (seconds)",
        default=29.0,
        min=0.01
    )
    fps: IntProperty(
        name="FPS",
        default=30,
        min=1
    )
    use_scene_range: BoolProperty(
        name="Use Scene Start/End",
        default=True
    )
    start_frame: IntProperty(
        name="Start Frame (override)",
        default=1,
        min=0
    )
    end_frame: IntProperty(
        name="End Frame (override)",
        default=250,
        min=0
    )
    export_selection_only: BoolProperty(
        name="Export Selection Only",
        default=False
    )
    generate_lsl: BoolProperty(
        name="Generate LSL Split Script",
        default=True
    )
    lsl_channel: IntProperty(
        name="LSL Channel",
        default=0
    )
    lsl_list_name: StringProperty(
        name="LSL List Name",
        default="oni_anim_list"
    )
    disable_rig_check: BoolProperty(
        name="Disable Onigiri Rig Check",
        default=False,
        description="Temporarily disable Onigiri rig checks during export (useful for non-Onigiri rigs)"
    )
    dry_run: BoolProperty(
        name="Dry Run (preview windows)",
        default=False
    )


class ONI_OT_sl_slice_export(bpy.types.Operator):
    bl_idname = "oni.sl_slice_export"
    bl_label = "Export SL Slices"
    bl_description = "Export Second Life .anim files in overlapping sliding windows"

    def execute(self, context):
        wm = context.window_manager
        s = wm.oni_sl_slice_settings

        # Ensure animutils is available
        if animutils is None:
            self.report({'ERROR'}, "Onigiri.animutils not available. Ensure Onigiri add-on is installed and enabled.")
            return {'CANCELLED'}

        # Determine armature: use active selected armature
        arm = None
        if context.active_object and context.active_object.type == 'ARMATURE':
            arm = context.active_object.name
        else:
            # try to find selected armature
            for obj in context.selected_objects:
                if obj.type == 'ARMATURE':
                    arm = obj.name
                    break
        if not arm:
            self.report({'ERROR'}, "No armature selected. Select an armature to export.")
            return {'CANCELLED'}

        fps = s.fps
        window_frames = max(1, int(round(s.window_seconds * fps)))
        step_frames = max(1, int(round(s.step_seconds * fps)))

        # SL limit: 60 seconds
        if s.window_seconds > 60.0:
            self.report({'ERROR'}, "Window length exceeds Second Life 60s limit")
            return {'CANCELLED'}

        if s.use_scene_range:
            start = context.scene.frame_start
            end = context.scene.frame_end
        else:
            start = s.start_frame
            end = s.end_frame

        if end <= start:
            self.report({'ERROR'}, "End frame must be greater than start frame")
            return {'CANCELLED'}

        out_dir = bpy.path.abspath(s.output_dir)
        os.makedirs(out_dir, exist_ok=True)

        starts = list(range(start, end - window_frames + 2, step_frames))
        last_start = end - window_frames + 1
        if len(starts) == 0 and last_start >= start:
            starts = [start]
        elif starts and starts[-1] < last_start:
            starts.append(last_start)

        preview_lines = []
        exported = []

        # Save original onigiri properties so we can restore them
        oni = getattr(context.scene, 'onigiri', None)
        if oni is None:
            self.report({'ERROR'}, "Scene property 'onigiri' not found. Ensure Onigiri is enabled.")
            return {'CANCELLED'}

        orig_start = getattr(oni, 'animation_start_frame', None)
        orig_end = getattr(oni, 'animation_end_frame', None)
        orig_fps = getattr(oni, 'animation_fps', None)
        orig_export_onigiri_disabled = getattr(oni, 'export_onigiri_disabled', None)

        try:
            for sf in starts:
                ef = sf + window_frames - 1
                if ef > end:
                    ef = end
                preview_lines.append((sf, ef))

            if s.dry_run:
                msg = "Preview windows: " + ", ".join([f"{a}-{b}" for a, b in preview_lines])
                self.report({'INFO'}, msg)
                print(msg)
                return {'FINISHED'}

            for i, (sf, ef) in enumerate(preview_lines):
                # set oni props
                oni.animation_start_frame = sf
                oni.animation_end_frame = ef
                oni.animation_fps = fps
                if s.disable_rig_check:
                    oni.export_onigiri_disabled = True

                filename = f"{s.file_prefix}_{sf:04d}-{ef:04d}.anim"
                filepath = os.path.join(out_dir, filename)

                # Call existing exporter
                try:
                    res = animutils.export_sl_anim(armature=arm, path=filepath)
                except Exception as e:
                    self.report({'ERROR'}, f"Export failed for {filename}: {e}")
                    return {'CANCELLED'}

                exported.append({'file': filename, 'start': sf, 'end': ef})
                self.report({'INFO'}, f"Exported {filename}")

        finally:
            # restore oni props
            if orig_start is not None:
                oni.animation_start_frame = orig_start
            if orig_end is not None:
                oni.animation_end_frame = orig_end
            if orig_fps is not None:
                oni.animation_fps = orig_fps
            if orig_export_onigiri_disabled is not None:
                oni.export_onigiri_disabled = orig_export_onigiri_disabled

        # Optionally write minimal LSL split script
        if s.generate_lsl and len(exported) > 0:
            lsl_path = os.path.join(out_dir, f"{s.file_prefix}_split.lsl")
            try:
                with open(lsl_path, 'w', encoding='utf8') as f:
                    f.write("// Auto-generated LSL split list for Onigiri exports\\n")
                    f.write("// Replace with your own playback logic\\n\\n")
                    anim_list = [e['file'] for e in exported]
                    times = [round((e['start'] - start) / fps, 3) for e in exported]
                    f.write("list ANIM_NAMES = [");
                    f.write(", ".join([f'\"{n}\"' for n in anim_list]));
                    f.write("];}\n");
                    f.write(f"list ANIM_TIMES = [");
                    f.write(", ".join([str(t) for t in times]));
                    f.write("];}\n\n");
                    f.write("// Example: iterate through the lists and play animations at given times\n");
                    f.write("// You will need to adapt this into a working LSL script with llSetTimerEvent or state machine.\n");
                self.report({'INFO'}, f"Wrote LSL split script: {lsl_path}")
            except Exception as e:
                self.report({'WARNING'}, f"Could not write LSL file: {e}")

        return {'FINISHED'}


class ONI_PT_sl_slice_panel(bpy.types.Panel):
    bl_label = "SL Slice Export"
    bl_idname = "SCENE_PT_oni_sl_slice"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'scene'

    def draw(self, context):
        layout = self.layout
        s = context.window_manager.oni_sl_slice_settings
        layout.prop(s, "output_dir")
        layout.prop(s, "file_prefix")
        layout.prop(s, "window_seconds")
        layout.prop(s, "step_seconds")
        layout.prop(s, "fps")
        layout.prop(s, "use_scene_range")
        col = layout.column()
        col.enabled = not s.use_scene_range
        col.prop(s, "start_frame")
        col.prop(s, "end_frame")
        layout.prop(s, "export_selection_only")
        layout.prop(s, "disable_rig_check")
        layout.prop(s, "dry_run")
        layout.separator()
        layout.prop(s, "generate_lsl")
        if s.generate_lsl:
            row = layout.row()
            row.prop(s, "lsl_list_name")
            row.prop(s, "lsl_channel")
        layout.operator("oni.sl_slice_export", icon='EXPORT')


classes = (
    OniSLSliceSettings,
    ONI_OT_sl_slice_export,
    ONI_PT_sl_slice_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.oni_sl_slice_settings = PointerProperty(type=OniSLSliceSettings)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.WindowManager.oni_sl_slice_settings


if __name__ == '__main__':
    register()
