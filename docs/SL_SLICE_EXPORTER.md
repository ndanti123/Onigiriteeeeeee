# SL Slice Exporter - User Guide

## Overview

The **SL Slice Exporter** is a tool for the Onigiri Blender add-on that automates the process of exporting long animations as a series of Second Life-compatible `.anim` files. Since Second Life has a 60-second limitation on animation files, this tool helps you break down longer animations into manageable segments with optional overlap for smooth transitions.

## Features

- **Automated Batch Export**: Automatically slice long animations into multiple time windows
- **Configurable Windows**: Set custom window length and step size for precise control
- **Overlapping Segments**: Create overlapping windows for smoother transitions between segments
- **LSL Script Generation**: Automatically generate an LSL script to play the animation sequence in Second Life
- **Dry Run Mode**: Preview what will be exported without actually writing files
- **Flexible Frame Ranges**: Use scene range or define custom start/end frames
- **Rig Check Control**: Option to disable rig validation for custom workflows

## Location

The SL Slice Exporter panel is located in the **Scene Properties** under the **"SL Slice Export"** section.

**Access Path**: Properties Panel → Scene Properties → SL Slice Export

## How to Use

### Basic Workflow

1. **Prepare Your Scene**:
   - Ensure you have an armature with an animation in your Blender scene
   - Set your desired animation range (or use the scene's default range)

2. **Open the SL Slice Export Panel**:
   - Navigate to the Scene Properties panel
   - Expand the "SL Slice Export" section

3. **Configure Output Settings**:
   - **Output Directory**: Choose where to save the `.anim` files
   - **File Prefix**: Set a prefix for your files (e.g., "dance" → "dance_0001-0030.anim")

4. **Set Window Parameters**:
   - **Window Length**: Duration of each segment in seconds (≤60 for SL compliance)
   - **Step Size**: Time between the start of consecutive windows
     - If Step < Window: Creates overlap (recommended for smooth transitions)
     - If Step = Window: No overlap (adjacent segments)
     - If Step > Window: Creates gaps (not recommended)
   - **FPS**: Frames per second for export (typically 24 or 30)

5. **Configure Frame Range**:
   - **Use Scene Range**: Enable to use the scene's start/end frames
   - Or disable and manually set **Start Frame** and **End Frame**

6. **Set Export Options**:
   - **Selection Only**: Export only the selected armature (if multiple exist)
   - **Disable Rig Check**: Skip validation (use only if you're certain your rig is compatible)
   - **Dry Run**: Preview the export windows without actually exporting

7. **LSL Script Options** (Optional):
   - **Generate LSL Script**: Enable to create an LSL script alongside the animations
   - **LSL Channel**: Communication channel for listen events (0 = public chat)
   - **LSL List Name**: Variable name for the animation list in the LSL script

8. **Export**:
   - Click **"Export SL Slice Animation"** to begin
   - Or click **"Preview Export Windows"** if Dry Run is enabled

### Example Configuration

**Scenario**: Export a 90-second animation as three 30-second segments with 1-second overlap

- **Window Length**: 30.0 seconds
- **Step Size**: 29.0 seconds (30 - 29 = 1 second overlap)
- **FPS**: 30
- **Total Animation**: 90 seconds (2700 frames)

**Result**: 
- Segment 1: frames 1-900 (0-30s) → `anim_0001-0900.anim`
- Segment 2: frames 871-1770 (29-59s) → `anim_0871-1770.anim`  
- Segment 3: frames 1741-2640 (58-88s) → `anim_1741-2640.anim`

Plus an LSL script: `anim_split.lsl`

## Understanding Windows and Overlap

The tool uses a **sliding window** approach:

- **Window Length** defines how many seconds of animation each file contains
- **Step Size** determines where the next window starts
- **Overlap** = Window Length - Step Size

### Overlap Benefits

Overlapping segments can help create smoother transitions in Second Life:
- The last second of one animation can blend with the first second of the next
- Useful for looping animations or continuous motion
- Typical overlap: 0.5 to 2 seconds

### No Overlap

Set **Step Size = Window Length** for non-overlapping, sequential segments:
- Best for distinct animation phases (walk → run → jump)
- Simpler LSL scripting
- Smaller total file size

## LSL Script Usage

If **Generate LSL Script** is enabled, the exporter creates a ready-to-use LSL script:

### Features of Generated Script:
- Plays animations in sequence
- Automatic timing based on animation durations
- Touch to start/stop
- Optional listen channel for remote control
- Loops back to the beginning when complete
- Owner-only control

### How to Use the LSL Script in Second Life:

1. **Upload All .anim Files**:
   - In Second Life, go to Build → Upload → Animation
   - Upload each generated `.anim` file to your inventory

2. **Create an Object**:
   - Rez a prim or object in-world
   - Right-click → Edit

3. **Add the Script**:
   - Upload the generated `.lsl` file (Build → Upload → Script)
   - Or create a new script and paste the content
   - Drag the script into the object's Contents

4. **Add Animations to Object**:
   - Drag all uploaded `.anim` files into the object's Contents tab
   - Ensure the names match exactly

5. **Test**:
   - Touch the object to start the animation sequence
   - Touch again to stop
   - If you set a listen channel: chat `/[channel] start` or `/[channel] stop`

## Tips and Best Practices

### Performance Tips

1. **File Size Considerations**:
   - Keep each segment ≤100KB if possible
   - Higher FPS = larger files
   - More bones animated = larger files
   - Consider FPS reduction for background animations

2. **Optimal Window Settings**:
   - 30-second windows work well for most animations
   - Shorter windows (15-20s) for complex, high-FPS animations
   - Longer windows (45-60s) for simple animations

3. **Overlap Recommendations**:
   - 0.5-1.0 seconds: Subtle transitions
   - 1.0-2.0 seconds: Smooth blending
   - 0 seconds: Clean cuts between distinct actions

### Troubleshooting

**Problem**: "Invalid output directory"
- **Solution**: Make sure the output directory exists and you have write permissions

**Problem**: "No armature found"
- **Solution**: Ensure you have at least one armature object in the scene

**Problem**: "No export windows could be calculated"
- **Solution**: Check that your end frame is greater than start frame and that window length fits in the range

**Problem**: Exported animations don't work in SL
- **Solution**: Verify your armature has SL-compatible bone names and structure
- **Solution**: Try enabling "Disable Rig Check" if you're using a non-standard rig

**Problem**: LSL script doesn't play animations
- **Solution**: Ensure all .anim files are in the object's Contents
- **Solution**: Verify animation names in the script match the uploaded file names (case-sensitive)
- **Solution**: Grant animation permissions when prompted

### Advanced Usage

**Custom LSL Scripts**: 
The generated LSL script is a starting point. You can modify it to:
- Add custom triggers (collision, sensor, etc.)
- Implement more complex sequencing
- Add sound effects or particle effects
- Integrate with other scripts

**Batch Processing**:
For multiple animations:
1. Set up your first animation with desired settings
2. Export it
3. Load the next animation action
4. Repeat with the same settings (they persist in the UI)

**Rig Checks**:
- The exporter uses Onigiri's `export_sl_anim()` function internally
- By default, it performs rig validation
- "Disable Rig Check" bypasses this (use with caution)
- All other Onigiri export settings are respected

## Technical Details

### What the Tool Does

The SL Slice Exporter is a **wrapper** around Onigiri's existing `export_sl_anim()` function:

1. Calculates export windows based on your settings
2. For each window:
   - Temporarily sets `scene.onigiri.animation_start_frame`
   - Temporarily sets `scene.onigiri.animation_end_frame`
   - Temporarily sets `scene.onigiri.animation_fps`
   - Calls `animutils.export_sl_anim()` to write the `.anim` file
   - Restores original scene settings
3. Optionally generates an LSL script with animation list and timings

### Scene Properties Modified (Temporarily)

During export, these properties are modified per window then restored:
- `scene.onigiri.animation_start_frame`
- `scene.onigiri.animation_end_frame`
- `scene.onigiri.animation_fps`
- `scene.onigiri.export_onigiri_disabled` (if "Disable Rig Check" is enabled)

All modifications are **reverted** after the export completes, even if an error occurs.

### File Naming Convention

Generated files follow this pattern:
```
{file_prefix}_{start_frame:04d}-{end_frame:04d}.anim
```

Example with prefix "walk":
- `walk_0001-0900.anim`
- `walk_0871-1770.anim`
- `walk_1741-2640.anim`
- `walk_split.lsl`

## Limitations and Caveats

1. **Second Life Limits**:
   - Maximum 60 seconds per `.anim` file
   - Recommended ≤100KB file size per animation
   - Some viewers may have lower limits

2. **Rig Compatibility**:
   - Your armature must have SL-compatible bone names
   - Use Onigiri's standard export for initial rig validation
   - The slice exporter inherits all Onigiri export limitations

3. **Memory Usage**:
   - Exporting many large windows can be memory-intensive
   - Consider exporting in batches if you experience issues

4. **No Mid-Export Modification**:
   - Don't modify the scene while export is in progress
   - Let the process complete before making changes

## Support and Feedback

For issues or feature requests related to the SL Slice Exporter:
- Check the Onigiri add-on documentation
- Verify your Blender version compatibility (Blender 3.x+)
- Review the console output for detailed error messages

## Version History

- **v1.0** (2025): Initial release
  - Basic window slicing functionality
  - LSL script generation
  - Dry run preview mode

---

**Author**: ndanti123  
**License**: Same as Onigiri add-on  
**Compatibility**: Blender 3.x+, Onigiri v3.0.5+
