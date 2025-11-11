"""
SL Slice Exporter - Second Life Animation Batch Exporter
=========================================================

This module provides automation for exporting long Blender animations as a series of 
Second Life .anim files in sliding/overlapping time windows.

Purpose:
--------
Second Life has a 60-second limitation on animation files. This tool helps export 
longer animations by automatically slicing them into shorter segments with optional 
overlap, and optionally generating an LSL script to play them sequentially in-world.

Features:
---------
- Export animations in configurable time windows (e.g., 30-second chunks)
- Configurable overlap between segments for smooth transitions
- Automatic file naming with frame range indicators
- Optional LSL script generation for in-world playback
- Dry-run mode to preview export windows without exporting
- Respects existing Onigiri export settings and rig validation

Usage:
------
1. Open your Blender scene with an armature and animation
2. Navigate to Scene Properties > "SL Slice Export" panel
3. Configure output directory, file prefix, and window settings
4. Optionally enable "Dry Run" to preview the export windows
5. Click "Export SL Slice Animation" to process

Important Notes:
----------------
- This is a wrapper around the existing export_sl_anim() function
- Temporarily modifies scene.onigiri animation frame properties per export
- Restores all modified settings after export
- Each segment must be ≤60 seconds to comply with SL limitations
- Consider file size limits (~100KB recommended) when setting FPS and window length
- Disable rig checks only if you're certain your rig is compatible

Author: ndanti123
License: Same as parent Onigiri add-on
"""

import bpy
import os
import math
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import StringProperty, FloatProperty, IntProperty, BoolProperty


class OniSLSliceSettings(PropertyGroup):
    """Property group for SL Slice Export settings stored on WindowManager"""
    
    output_dir: StringProperty(
        name="Output Directory",
        description="Directory where .anim files will be saved",
        default="",
        subtype='DIR_PATH'
    )
    
    file_prefix: StringProperty(
        name="File Prefix",
        description="Prefix for exported animation files (e.g., 'my_anim' → 'my_anim_0001-0030.anim')",
        default="anim"
    )
    
    window_seconds: FloatProperty(
        name="Window Length (seconds)",
        description="Length of each animation segment in seconds (must be ≤60 for SL)",
        default=30.0,
        min=0.1,
        max=60.0
    )
    
    step_seconds: FloatProperty(
        name="Step Size (seconds)",
        description="Time between window start frames (use < window for overlap). Example: window=30, step=29 gives 1s overlap",
        default=29.0,
        min=0.1,
        max=60.0
    )
    
    fps: IntProperty(
        name="FPS",
        description="Frames per second for animation export",
        default=30,
        min=1,
        max=120
    )
    
    use_scene_range: BoolProperty(
        name="Use Scene Range",
        description="Use scene start/end frames. Disable to set custom range",
        default=True
    )
    
    start_frame: IntProperty(
        name="Start Frame",
        description="First frame to export (only used if 'Use Scene Range' is disabled)",
        default=1,
        min=0
    )
    
    end_frame: IntProperty(
        name="End Frame",
        description="Last frame to export (only used if 'Use Scene Range' is disabled)",
        default=250,
        min=1
    )
    
    export_selection_only: BoolProperty(
        name="Selection Only",
        description="Export only selected armature (first selected). If disabled, uses active object",
        default=False
    )
    
    generate_lsl: BoolProperty(
        name="Generate LSL Script",
        description="Generate an LSL script to play the animation sequence in Second Life",
        default=True
    )
    
    lsl_channel: IntProperty(
        name="LSL Channel",
        description="Communication channel for LSL script (for listen events)",
        default=0,
        min=-2147483648,
        max=2147483647
    )
    
    lsl_list_name: StringProperty(
        name="LSL List Name",
        description="Variable name for animation list in LSL script",
        default="oni_anim_list"
    )
    
    disable_rig_check: BoolProperty(
        name="Disable Rig Check",
        description="Skip rig validation checks during export (use with caution)",
        default=False
    )
    
    dry_run: BoolProperty(
        name="Dry Run",
        description="Preview export windows without actually exporting files",
        default=False
    )


class ONI_OT_sl_slice_export(Operator):
    """Export animation in overlapping time windows as multiple SL .anim files"""
    bl_idname = "oni.sl_slice_export"
    bl_label = "Export SL Slice Animation"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        # Need at least one armature in the scene
        return any(obj.type == 'ARMATURE' for obj in bpy.data.objects)
    
    def execute(self, context):
        settings = context.window_manager.oni_sl_slice_settings
        
        # Validate output directory
        if not settings.output_dir or not os.path.isdir(settings.output_dir):
            self.report({'ERROR'}, "Invalid output directory. Please select a valid folder.")
            return {'CANCELLED'}
        
        # Get armature
        if settings.export_selection_only and context.selected_objects:
            armatures = [obj for obj in context.selected_objects if obj.type == 'ARMATURE']
            if not armatures:
                self.report({'ERROR'}, "No armature selected. Please select an armature.")
                return {'CANCELLED'}
            arm_obj = armatures[0]
        else:
            arm_obj = context.active_object
            if not arm_obj or arm_obj.type != 'ARMATURE':
                # Try to find any armature
                armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
                if not armatures:
                    self.report({'ERROR'}, "No armature found in scene.")
                    return {'CANCELLED'}
                arm_obj = armatures[0]
        
        # Get frame range
        if settings.use_scene_range:
            start_frame = context.scene.frame_start
            end_frame = context.scene.frame_end
        else:
            start_frame = settings.start_frame
            end_frame = settings.end_frame
        
        if end_frame <= start_frame:
            self.report({'ERROR'}, f"End frame ({end_frame}) must be greater than start frame ({start_frame}).")
            return {'CANCELLED'}
        
        # Calculate window parameters
        window_frames = round(settings.window_seconds * settings.fps)
        step_frames = round(settings.step_seconds * settings.fps)
        
        if window_frames < 1:
            self.report({'ERROR'}, f"Window length too small: results in {window_frames} frames.")
            return {'CANCELLED'}
        
        if step_frames < 1:
            self.report({'ERROR'}, f"Step size too small: results in {step_frames} frames.")
            return {'CANCELLED'}
        
        # Calculate export windows
        windows = []
        current_start = start_frame
        while current_start <= end_frame - window_frames + 1:
            window_end = min(current_start + window_frames - 1, end_frame)
            windows.append((current_start, window_end))
            current_start += step_frames
        
        # If no windows could be computed but we have frames, export as single window
        if not windows and end_frame >= start_frame:
            windows.append((start_frame, end_frame))
        
        if not windows:
            self.report({'ERROR'}, "No export windows could be calculated. Check your frame range and window settings.")
            return {'CANCELLED'}
        
        # Dry run mode - just report what would be exported
        if settings.dry_run:
            report_lines = [f"DRY RUN - {len(windows)} window(s) would be exported:"]
            for i, (ws, we) in enumerate(windows, 1):
                duration = (we - ws + 1) / settings.fps
                filename = f"{settings.file_prefix}_{ws:04d}-{we:04d}.anim"
                report_lines.append(f"  {i}. Frames {ws}-{we} ({duration:.2f}s): {filename}")
            
            self.report({'INFO'}, "\n".join(report_lines))
            print("\n".join(report_lines))
            return {'FINISHED'}
        
        # Store original scene settings to restore later
        oni = context.scene.onigiri
        original_start = oni.animation_start_frame
        original_end = oni.animation_end_frame
        original_fps = oni.animation_fps
        original_disable_check = oni.export_onigiri_disabled
        
        # Prepare for LSL generation
        anim_files = []
        anim_durations = []
        
        try:
            # Export each window
            for i, (window_start, window_end) in enumerate(windows, 1):
                # Update progress
                progress_msg = f"Exporting window {i}/{len(windows)}: frames {window_start}-{window_end}"
                print(progress_msg)
                
                # Set scene properties for this export
                oni.animation_start_frame = window_start
                oni.animation_end_frame = window_end
                oni.animation_fps = settings.fps
                
                if settings.disable_rig_check:
                    oni.export_onigiri_disabled = True
                
                # Build filename
                filename = f"{settings.file_prefix}_{window_start:04d}-{window_end:04d}.anim"
                filepath = os.path.join(settings.output_dir, filename)
                
                # Call existing export function
                from .. import animutils
                try:
                    animutils.export_sl_anim(armature=arm_obj.name, path=filepath)
                    
                    # Track for LSL generation
                    anim_files.append(filename)
                    duration = (window_end - window_start + 1) / settings.fps
                    anim_durations.append(duration)
                    
                    print(f"  → Saved: {filename}")
                    
                except Exception as e:
                    self.report({'ERROR'}, f"Failed to export window {i}: {str(e)}")
                    print(f"Export error: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Generate LSL script if requested
            if settings.generate_lsl and anim_files:
                lsl_path = os.path.join(settings.output_dir, f"{settings.file_prefix}_split.lsl")
                self._generate_lsl_script(lsl_path, anim_files, anim_durations, settings)
                print(f"Generated LSL script: {lsl_path}")
            
            self.report({'INFO'}, f"Successfully exported {len(windows)} animation segment(s)")
            return {'FINISHED'}
            
        finally:
            # Always restore original settings
            oni.animation_start_frame = original_start
            oni.animation_end_frame = original_end
            oni.animation_fps = original_fps
            oni.export_onigiri_disabled = original_disable_check
    
    def _generate_lsl_script(self, filepath, anim_files, durations, settings):
        """Generate a simple LSL script to play animation sequence"""
        
        # Build animation list string
        anim_list_str = ", ".join(f'"{name}"' for name in anim_files)
        
        # Build duration list string (in seconds)
        duration_list_str = ", ".join(f"{dur:.2f}" for dur in durations)
        
        # Simple LSL template
        lsl_code = f"""// SL Animation Sequence Player
// Generated by Onigiri SL Slice Exporter
// Author: ndanti123
//
// This script plays a sequence of animations exported in time-sliced windows.
// Upload all .anim files to your inventory, then add them to the object with this script.

list {settings.lsl_list_name} = [{anim_list_str}];
list anim_durations = [{duration_list_str}];  // Duration of each animation in seconds

integer current_index = 0;
integer is_playing = FALSE;
integer listen_handle = -1;

play_next_animation() {{
    if (current_index < llGetListLength({settings.lsl_list_name})) {{
        string anim_name = llList2String({settings.lsl_list_name}, current_index);
        float duration = llList2Float(anim_durations, current_index);
        
        llRequestPermissions(llGetOwner(), PERMISSION_TRIGGER_ANIMATION);
        llStartAnimation(anim_name);
        
        llOwnerSay("Playing: " + anim_name + " (" + (string)duration + "s)");
        
        // Schedule next animation
        current_index++;
        llSetTimerEvent(duration);
    }} else {{
        // Sequence complete, loop back to start
        current_index = 0;
        llSetTimerEvent(0.0);
        is_playing = FALSE;
        llOwnerSay("Animation sequence complete.");
    }}
}}

stop_animations() {{
    integer i;
    for (i = 0; i < llGetListLength({settings.lsl_list_name}); i++) {{
        llStopAnimation(llList2String({settings.lsl_list_name}, i));
    }}
    llSetTimerEvent(0.0);
    current_index = 0;
    is_playing = FALSE;
}}

default {{
    state_entry() {{
        llOwnerSay("Animation sequencer ready. Touch to start/stop.");
        if ({settings.lsl_channel} != 0) {{
            listen_handle = llListen({settings.lsl_channel}, "", llGetOwner(), "");
            llOwnerSay("Listening on channel " + (string){settings.lsl_channel} + " for 'start' and 'stop' commands.");
        }}
    }}
    
    touch_start(integer num) {{
        if (llDetectedKey(0) == llGetOwner()) {{
            if (!is_playing) {{
                is_playing = TRUE;
                current_index = 0;
                play_next_animation();
            }} else {{
                stop_animations();
                llOwnerSay("Stopped.");
            }}
        }}
    }}
    
    listen(integer channel, string name, key id, string message) {{
        if (id == llGetOwner()) {{
            if (message == "start" && !is_playing) {{
                is_playing = TRUE;
                current_index = 0;
                play_next_animation();
            }} else if (message == "stop") {{
                stop_animations();
            }}
        }}
    }}
    
    timer() {{
        play_next_animation();
    }}
    
    run_time_permissions(integer perm) {{
        if (perm & PERMISSION_TRIGGER_ANIMATION) {{
            // Permission granted, animation will play
        }}
    }}
}}
"""
        
        # Write LSL script
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(lsl_code)


class SCENE_PT_oni_sl_slice(Panel):
    """Panel for SL Slice Export in Scene properties"""
    bl_label = "SL Slice Export"
    bl_idname = "SCENE_PT_oni_sl_slice"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        settings = context.window_manager.oni_sl_slice_settings
        
        # Output settings
        box = layout.box()
        box.label(text="Output Settings:", icon='EXPORT')
        box.prop(settings, "output_dir")
        box.prop(settings, "file_prefix")
        
        # Window settings
        box = layout.box()
        box.label(text="Window Settings:", icon='TIME')
        box.prop(settings, "window_seconds")
        box.prop(settings, "step_seconds")
        
        # Display overlap info
        overlap = settings.window_seconds - settings.step_seconds
        if overlap > 0:
            row = box.row()
            row.label(text=f"Overlap: {overlap:.2f}s", icon='INFO')
        elif overlap < 0:
            row = box.row()
            row.label(text=f"Gap: {abs(overlap):.2f}s", icon='ERROR')
        
        box.prop(settings, "fps")
        
        # Frame range settings
        box = layout.box()
        box.label(text="Frame Range:", icon='PREVIEW_RANGE')
        box.prop(settings, "use_scene_range")
        
        if not settings.use_scene_range:
            row = box.row(align=True)
            row.prop(settings, "start_frame")
            row.prop(settings, "end_frame")
        else:
            row = box.row()
            row.label(text=f"Scene: {context.scene.frame_start} - {context.scene.frame_end}")
        
        # Export options
        box = layout.box()
        box.label(text="Export Options:", icon='PREFERENCES')
        box.prop(settings, "export_selection_only")
        box.prop(settings, "disable_rig_check")
        box.prop(settings, "dry_run")
        
        # LSL generation settings
        box = layout.box()
        box.label(text="LSL Script Generation:", icon='TEXT')
        box.prop(settings, "generate_lsl")
        
        if settings.generate_lsl:
            box.prop(settings, "lsl_channel")
            box.prop(settings, "lsl_list_name")
        
        # Export button
        layout.separator()
        row = layout.row()
        row.scale_y = 1.5
        
        if settings.dry_run:
            row.operator("oni.sl_slice_export", text="Preview Export Windows", icon='HIDE_OFF')
        else:
            row.operator("oni.sl_slice_export", text="Export SL Slice Animation", icon='EXPORT')
        
        # Help text
        layout.separator()
        box = layout.box()
        box.label(text="Help:", icon='QUESTION')
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="• Window: length of each segment (≤60s for SL)")
        col.label(text="• Step: time between segments (< window = overlap)")
        col.label(text="• Dry Run: preview without exporting")
        col.label(text="• LSL script plays segments sequentially")


# Registration
classes = (
    OniSLSliceSettings,
    ONI_OT_sl_slice_export,
    SCENE_PT_oni_sl_slice,
)


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)
    
    # Register property group on WindowManager
    bpy.types.WindowManager.oni_sl_slice_settings = bpy.props.PointerProperty(type=OniSLSliceSettings)


def unregister():
    from bpy.utils import unregister_class
    
    # Unregister property group
    del bpy.types.WindowManager.oni_sl_slice_settings
    
    for cls in reversed(classes):
        unregister_class(cls)


if __name__ == "__main__":
    register()
