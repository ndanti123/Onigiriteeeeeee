import json
import math
import os

import bpy
import mathutils
from bpy_extras.io_utils import ImportHelper

from . import anim
from . import animutils
from .presets import skeleton as skel


def _to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _normalized_time(seconds, settings):
    t = max(0.0, seconds)
    if settings.time_mode == 'FPS_FRAMES' and settings.fps > 0:
        frame = round(t * settings.fps)
        t = frame / settings.fps
    return t


def _pack_quat_xyz(x, y, z):
    return (
        animutils.F32_to_U16(x, -1.0, 1.0),
        animutils.F32_to_U16(y, -1.0, 1.0),
        animutils.F32_to_U16(z, -1.0, 1.0),
    )


def _rotation_triplet_to_packed(value, settings):
    x = _to_float(value[0] if len(value) > 0 else 0.0)
    y = _to_float(value[1] if len(value) > 1 else 0.0)
    z = _to_float(value[2] if len(value) > 2 else 0.0)

    if settings.rotation_mode == 'RAW_SL_QUAT_XYZ':
        return _pack_quat_xyz(x, y, z)

    if settings.rotation_mode == 'QUAT_XYZ_INFER_W':
        xyz_len_sq = x * x + y * y + z * z
        w = math.sqrt(max(0.0, 1.0 - xyz_len_sq))
        if settings.quat_w_sign == 'NEGATIVE':
            w = -w
        quat = mathutils.Quaternion((w, x, y, z)).normalized()
        return _pack_quat_xyz(quat.x, quat.y, quat.z)

    if settings.rotation_mode == 'EULER_DEGREES':
        x = math.radians(x)
        y = math.radians(y)
        z = math.radians(z)

    euler = mathutils.Euler((x, y, z), settings.euler_order)
    quat = euler.to_quaternion().normalized()
    return _pack_quat_xyz(quat.x, quat.y, quat.z)


def _position_triplet_to_packed(value, settings):
    scale = settings.location_scale
    x = _to_float(value[0] if len(value) > 0 else 0.0) * scale
    y = _to_float(value[1] if len(value) > 1 else 0.0) * scale
    z = _to_float(value[2] if len(value) > 2 else 0.0) * scale

    pelvis_range = animutils.LL_MAX_PELVIS_OFFSET
    return (
        animutils.F32_to_U16(x / pelvis_range, -1.0, 1.0),
        animutils.F32_to_U16(y / pelvis_range, -1.0, 1.0),
        animutils.F32_to_U16(z / pelvis_range, -1.0, 1.0),
    )


def load_json_animation(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_bone_data_from_json(data, settings, armature):
    joints = data.get('joints') or []

    duration = _to_float(data.get('duration'), 0.0)
    max_key_time = 0.0
    for joint in joints:
        for key in joint.get('rotationKeys') or []:
            max_key_time = max(max_key_time, _to_float(key.get('time'), 0.0))
        for key in joint.get('positionKeys') or []:
            max_key_time = max(max_key_time, _to_float(key.get('time'), 0.0))
    duration = max(duration, max_key_time, 0.001)

    valid_sl_bones = set(skel.avatar_skeleton.keys())
    rig_bones = set(armature.pose.bones.keys())

    unknown_sl = []
    missing_in_armature = []

    bone_data = {}
    bone_list = []
    joint_priorities = {}

    for joint in joints:
        bone = str(joint.get('name', '')).strip()
        if not bone:
            continue

        if bone not in valid_sl_bones:
            unknown_sl.append(bone)
            continue

        if bone not in rig_bones:
            missing_in_armature.append(bone)
            continue

        rot_keys = sorted(joint.get('rotationKeys') or [], key=lambda k: _to_float(k.get('time'), 0.0))
        pos_keys = sorted(joint.get('positionKeys') or [], key=lambda k: _to_float(k.get('time'), 0.0))

        if not rot_keys and not pos_keys:
            continue

        bone_data[bone] = {}
        joint_priorities[bone] = _to_int(joint.get('priority'), _to_int(data.get('priority'), 3))

        if rot_keys:
            bone_data[bone]['rot'] = {'values': [], 'times': []}
            for key in rot_keys:
                raw_time = _to_float(key.get('time'), 0.0)
                norm_time = min(_normalized_time(raw_time, settings), duration)
                packed_time = animutils.F32_to_U16(norm_time, 0.0, duration)
                packed_rot = _rotation_triplet_to_packed(key.get('value') or [], settings)
                bone_data[bone]['rot']['times'].append(packed_time)
                bone_data[bone]['rot']['values'].append(packed_rot)

        if pos_keys:
            is_pelvis = bone.lower() == 'mpelvis'.lower()
            if (is_pelvis and settings.include_pelvis_location) or (not is_pelvis and settings.include_non_pelvis_location):
                bone_data[bone]['loc'] = {'values': [], 'times': []}
                for key in pos_keys:
                    raw_time = _to_float(key.get('time'), 0.0)
                    norm_time = min(_normalized_time(raw_time, settings), duration)
                    packed_time = animutils.F32_to_U16(norm_time, 0.0, duration)
                    packed_pos = _position_triplet_to_packed(key.get('value') or [], settings)
                    bone_data[bone]['loc']['times'].append(packed_time)
                    bone_data[bone]['loc']['values'].append(packed_pos)

        if bone_data[bone].get('rot') or bone_data[bone].get('loc'):
            bone_list.append(bone)
        else:
            del bone_data[bone]

    loop_in_point = _to_float(data.get('loopInPoint'), 0.0)
    loop_out_point = _to_float(data.get('loopOutPoint'), duration)
    ease_in = _to_float(data.get('easeInTime'), 0.0)
    ease_out = _to_float(data.get('easeOutTime'), 0.0)
    loop_value = bool(data.get('loop', False))
    base_priority = _to_int(data.get('priority'), 3)

    if not settings.use_json_loop_settings:
        loop_value = settings.loop
        loop_in_point = settings.loop_in_point
        loop_out_point = settings.loop_out_point
        ease_in = settings.ease_in_time
        ease_out = settings.ease_out_time
        base_priority = settings.base_priority

    loop_in_point = min(max(0.0, _normalized_time(loop_in_point, settings)), duration)
    loop_out_point = min(max(loop_in_point, _normalized_time(loop_out_point, settings)), duration)

    return {
        'bone_data': bone_data,
        'bone_list': bone_list,
        'duration': duration,
        'loop': loop_value,
        'loop_in_point': loop_in_point,
        'loop_out_point': loop_out_point,
        'ease_in': max(0.0, ease_in),
        'ease_out': max(0.0, ease_out),
        'base_priority': max(-1, min(6, base_priority)),
        'joint_priorities': joint_priorities,
        'unknown_sl': sorted(set(unknown_sl)),
        'missing_in_armature': sorted(set(missing_in_armature)),
    }


def convert_json_to_sl_anim(context, json_path, output_path, settings):
    if not context.selected_objects or context.selected_objects[0].type != 'ARMATURE':
        return {'ok': False, 'message': 'Select one armature before exporting.'}

    armature = context.selected_objects[0]
    data = load_json_animation(json_path)
    converted = build_bone_data_from_json(data=data, settings=settings, armature=armature)

    bone_data = converted['bone_data']
    bone_list = converted['bone_list']

    if not bone_list:
        return {'ok': False, 'message': 'No valid SL joints with keys were found in JSON.', 'details': converted}

    if len(bone_list) != len(bone_data):
        return {'ok': False, 'message': 'Internal mismatch between joint list and data.', 'details': converted}

    scene = context.scene
    oni = scene.onigiri
    oni_anim = scene.oni_anim

    original = {
        'animation_fps': oni.animation_fps,
        'anim_loop': bool(oni_anim.anim_loop),
        'anim_ease_in_duration': float(oni_anim.anim_ease_in_duration),
        'anim_ease_out_duration': float(oni_anim.anim_ease_out_duration),
        'anim_base_priority': int(oni_anim.anim_base_priority),
        'anim_emote_name': str(oni_anim.anim_emote_name),
    }

    original_joint_priority = {}

    try:
        oni.animation_fps = settings.fps
        oni_anim.anim_loop = converted['loop']
        oni_anim.anim_ease_in_duration = converted['ease_in']
        oni_anim.anim_ease_out_duration = converted['ease_out']
        oni_anim.anim_base_priority = converted['base_priority']

        if data.get('uuid'):
            oni_anim.anim_emote_name = str(data.get('uuid'))[:63]

        if settings.use_json_joint_priorities:
            for bone in bone_list:
                pbone = armature.pose.bones[bone]
                original_joint_priority[bone] = {
                    'priority_enabled': pbone.get('priority_enabled'),
                    'priority': pbone.get('priority'),
                }
                pbone['priority_enabled'] = 1
                pbone['priority'] = converted['joint_priorities'].get(bone, converted['base_priority'])

        result = animutils.write_animation(
            armature=armature.name,
            bone_data=bone_data,
            bone_list=bone_list,
            frame_current=scene.frame_current,
            total_time=converted['duration'],
            loop_in_point=converted['loop_in_point'],
            loop_out_point=converted['loop_out_point'],
            path=output_path,
        )
    finally:
        oni.animation_fps = original['animation_fps']
        oni_anim.anim_loop = original['anim_loop']
        oni_anim.anim_ease_in_duration = original['anim_ease_in_duration']
        oni_anim.anim_ease_out_duration = original['anim_ease_out_duration']
        oni_anim.anim_base_priority = original['anim_base_priority']
        oni_anim.anim_emote_name = original['anim_emote_name']

        if settings.use_json_joint_priorities:
            for bone, state in original_joint_priority.items():
                pbone = armature.pose.bones[bone]
                if state['priority_enabled'] is None:
                    pbone.pop('priority_enabled', None)
                else:
                    pbone['priority_enabled'] = state['priority_enabled']

                if state['priority'] is None:
                    pbone.pop('priority', None)
                else:
                    pbone['priority'] = state['priority']

    bones_with_rot = sum(1 for bone in bone_list if bone_data[bone].get('rot'))
    bones_with_loc = sum(1 for bone in bone_list if bone_data[bone].get('loc'))

    print('JSON to SL anim export summary:')
    print(' - Input JSON:', json_path)
    print(' - Output ANIM:', output_path)
    print(' - Duration:', converted['duration'])
    print(' - Header num_joints:', len(bone_list))
    print(' - Bones with rotation keys:', bones_with_rot)
    print(' - Bones with location keys:', bones_with_loc)

    if converted['unknown_sl']:
        print(' - Warning: joints not in SL skeleton (skipped):', converted['unknown_sl'])
    if converted['missing_in_armature']:
        print(' - Warning: joints not found in selected armature (skipped):', converted['missing_in_armature'])

    return {
        'ok': bool(result),
        'message': 'Exported JSON animation to SL .anim.' if result else 'Export failed in writer.',
        'details': converted,
        'output_path': output_path,
        'bones_with_rot': bones_with_rot,
        'bones_with_loc': bones_with_loc,
    }


def json_anim_self_check(json_path, output_path='', armature_name=''):
    ctx = bpy.context

    if armature_name:
        arm_obj = bpy.data.objects.get(armature_name)
        if arm_obj is None or arm_obj.type != 'ARMATURE':
            return {'ok': False, 'message': 'armature_name is not a valid armature object.'}
        for obj in ctx.selected_objects:
            obj.select_set(False)
        arm_obj.select_set(True)
        ctx.view_layer.objects.active = arm_obj

    if not output_path:
        root, _ = os.path.splitext(json_path)
        output_path = root + '_selfcheck.anim'

    settings = ctx.scene.oni_json_anim
    result = convert_json_to_sl_anim(ctx, json_path=json_path, output_path=output_path, settings=settings)
    if not result.get('ok'):
        return result

    decoded = anim.load_anim(output_path)
    if not decoded:
        return {'ok': False, 'message': 'Exported file could not be decoded by anim.load_anim.', 'output_path': output_path}

    joints = decoded.get('joints', {})
    joint_count = len(joints)
    rot_keys = sum(len(joints[j].get('rot', [])) for j in joints)
    loc_keys = sum(len(joints[j].get('loc', [])) for j in joints)

    report = {
        'ok': joint_count > 0 and (rot_keys + loc_keys) > 0,
        'output_path': output_path,
        'joint_count': joint_count,
        'rotation_keys': rot_keys,
        'location_keys': loc_keys,
    }
    print('json_anim_self_check:', report)
    return report


class OnigiriJsonAnimSettings(bpy.types.PropertyGroup):
    output_path: bpy.props.StringProperty(
        name='Output .anim',
        description='Target Second Life .anim file path',
        default='',
        subtype='FILE_PATH',
    )

    fps: bpy.props.FloatProperty(
        name='FPS',
        description='FPS for optional time quantization',
        default=30.0,
        min=1.0,
        max=240.0,
    )

    time_mode: bpy.props.EnumProperty(
        name='Time Mode',
        items=(
            ('SL_SECONDS', 'SL seconds', 'Use JSON key times as seconds'),
            ('FPS_FRAMES', 'Quantize to FPS', 'Convert key time to frame and back to seconds using FPS'),
        ),
        default='SL_SECONDS',
    )

    rotation_mode: bpy.props.EnumProperty(
        name='Rotation Mode',
        items=(
            ('EULER_DEGREES', 'Euler Degrees', 'Treat rotation triplets as Euler angles in degrees'),
            ('EULER_RADIANS', 'Euler Radians', 'Treat rotation triplets as Euler angles in radians'),
            ('QUAT_XYZ_INFER_W', 'Quaternion XYZ (+W)', 'Treat values as quaternion xyz and infer w'),
            ('RAW_SL_QUAT_XYZ', 'Raw SL packed quat xyz', 'Treat values as quaternion xyz in [-1,1] and pack directly'),
        ),
        default='EULER_DEGREES',
    )

    euler_order: bpy.props.EnumProperty(
        name='Euler Order',
        items=(
            ('XYZ', 'XYZ', ''),
            ('XZY', 'XZY', ''),
            ('YXZ', 'YXZ', ''),
            ('YZX', 'YZX', ''),
            ('ZXY', 'ZXY', ''),
            ('ZYX', 'ZYX', ''),
        ),
        default='XYZ',
    )

    quat_w_sign: bpy.props.EnumProperty(
        name='Inferred W Sign',
        items=(
            ('POSITIVE', 'Positive', 'Use +sqrt for inferred quaternion w'),
            ('NEGATIVE', 'Negative', 'Use -sqrt for inferred quaternion w'),
        ),
        default='POSITIVE',
    )

    location_scale: bpy.props.FloatProperty(
        name='Location Scale',
        description='Scale factor applied to JSON position keys before SL packing',
        default=1.0,
        min=0.0001,
        soft_max=1000.0,
    )

    include_pelvis_location: bpy.props.BoolProperty(
        name='Include Pelvis Position',
        description='Export mPelvis position keys from JSON',
        default=True,
    )

    include_non_pelvis_location: bpy.props.BoolProperty(
        name='Include Other Position Keys',
        description='Export position keys for non-pelvis joints',
        default=False,
    )

    use_json_loop_settings: bpy.props.BoolProperty(
        name='Use Loop/Ease/Priority From JSON',
        default=True,
    )

    loop: bpy.props.BoolProperty(name='Loop', default=False)
    loop_in_point: bpy.props.FloatProperty(name='Loop In', default=0.0, min=0.0)
    loop_out_point: bpy.props.FloatProperty(name='Loop Out', default=0.0, min=0.0)
    ease_in_time: bpy.props.FloatProperty(name='Ease In', default=0.0, min=0.0)
    ease_out_time: bpy.props.FloatProperty(name='Ease Out', default=0.0, min=0.0)
    base_priority: bpy.props.IntProperty(name='Base Priority', default=3, min=-1, max=6)

    use_json_joint_priorities: bpy.props.BoolProperty(
        name='Use Joint Priority From JSON',
        description='Apply each JSON joint priority while exporting',
        default=True,
    )


class OnigiriJsonToSlAnim(bpy.types. SL .anim'
    bl_description = 'Convert JSON animation format to Second Life .anim using Onigiri writer'

    filter_glob: bpy.props.StringProperty(default='*.json', options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        if len(context.selected_objects) != 1:
            return False
        return context.selected_objects[0].type == 'ARMATURE'

    def invoke(self, context, event):
        settings = context.scene.oni_json_anim
        if settings.output_path:
            self.filepath = settings.output_path.replace('.anim', '.json')
        return super().invoke(context, event)

    def execute(self, context):
        settings = context.scene.oni_json_anim

        output_path = settings.output_path.strip()
        if not output_path:
            root, _ = os.path.splitext(self.filepath)
            output_path = root + '.anim'

        if not output_path.lower().endswith('.anim'):
            output_path += '.anim'

        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.isdir(output_dir):
            self.report({'ERROR'}, 'Output directory does not exist.')
            return {'CANCELLED'}

        result = convert_json_to_sl_anim(
            context,
            json_path=self.filepath,
            output_path=output_path,
            settings=settings,
        )

        if not result.get('ok'):
            self.report({'ERROR'}, result.get('message', 'JSON export failed'))
            return {'CANCELLED'}

        settings.output_path = output_path

        details = result.get('details', {})
        if details.get('unknown_sl'):
            self.report({'WARNING'}, 'Some joints were skipped (not in SL skeleton), see console.')
        elif details.get('missing_in_armature'):
            self.report({'WARNING'}, 'Some joints were skipped (missing in rig), see console.')
        else:
            self.report({'INFO'}, 'Export complete: ' + output_path)

        return {'FINISHED'}
