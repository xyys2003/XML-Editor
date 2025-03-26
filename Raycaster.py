import numpy as np
from typing import List, Optional, Tuple, Dict
from PyQt5.QtCore import QObject, pyqtSignal
from Geomentry import TransformMode, Material, GeometryType, Geometry, GeometryGroup, OperationMode


def euler_angles_to_matrix(angles):
    """将欧拉角转换为旋转矩阵（参考网页1的Eigen实现）"""
    Rx = np.array([[1, 0, 0],
                  [0, np.cos(angles[0]), -np.sin(angles[0])],
                  [0, np.sin(angles[0]), np.cos(angles[0])]])
    
    Ry = np.array([[np.cos(angles[1]), 0, np.sin(angles[1])],
                  [0, 1, 0],
                  [-np.sin(angles[1]), 0, np.cos(angles[1])]])
    
    Rz = np.array([[np.cos(angles[2]), -np.sin(angles[2]), 0],
                  [np.sin(angles[2]), np.cos(angles[2]), 0],
                  [0, 0, 1]])
    
    rotation_3x3 = Rz @ Ry @ Rx
    
    # 扩展为4x4齐次矩阵
    matrix_4x4 = np.eye(4)
    matrix_4x4[:3, :3] = rotation_3x3
    return matrix_4x4



class RaycastResult:
    __slots__ = ('geometry', 'world_position', 'distance', 'local_position', 'uv_coords','ray_origin', 'ray_direction')
    
    def __init__(self):
        self.geometry: Optional[Geometry] = None
        self.world_position: Optional[np.ndarray] = None
        self.distance: float = float('inf')
        self.local_position: Optional[np.ndarray] = None
        self.uv_coords: Tuple[float, float] = (0.0, 0.0)
        self.ray_origin: np.ndarray = None    # 射线起点[2](@ref)
        self.ray_direction: np.ndarray = None # 射线方向向量

class GeometryRaycaster:
    def __init__(self, camera_config: Dict, geometries: List[Geometry | GeometryGroup]):  # 更新类型注解
        self._validate_camera_config(camera_config)
        self.camera = camera_config
        self.geometries = geometries
        self._aabb_cache = {}

    def _validate_camera_config(self, config: Dict):
        """验证相机配置完整性"""
        required_keys = {'position', 'view', 'projection', 'viewport', 'orthographic'}
        if not required_keys.issubset(config.keys()):
            missing = required_keys - config.keys()
            raise KeyError(f"Missing camera config keys: {missing}")

        # 处理视口格式（兼容四元组和二元组）
        viewport = config['viewport']
        if len(viewport) not in (2, 4):
            raise ValueError(f"Invalid viewport format: {viewport}")
        config['viewport'] = viewport[-2:]  # 始终存储为(w, h)

    def cast_ray(self, screen_pos: Tuple[float, float]) -> Optional[RaycastResult]:
        """投射射线并检测与几何体的交点"""
        origin, direction = self._generate_ray(screen_pos)
        result = RaycastResult()
        result.distance = float('inf')
        
        # 递归检查所有几何体（包括组中的几何体）
        self._check_objects_recursive(self.geometries, origin, direction, result)
        
        result.ray_origin = origin.copy() if origin is not None else np.zeros(3)
        result.ray_direction = direction.copy() if direction is not None else np.zeros(3)
        
        return result if result.geometry else None

    def _check_objects_recursive(self, objects, origin, direction, result):
        """递归检查对象及其子对象与射线的交点
        Args:
            objects: 要检查的对象列表
            origin: 射线起点
            direction: 射线方向
            result: 当前的检测结果
        """
        for obj in objects:
            if isinstance(obj, GeometryGroup):
                # 如果是组，递归检查其子对象
                self._check_objects_recursive(obj.children, origin, direction, result)
            else:
                # 获取几何体数据
                center = obj.position
                size = obj.size
                
                # 将欧拉角转换为旋转矩阵
                rotation_matrix = euler_angles_to_matrix(np.radians(obj.rotation))[:3, :3]
                
                # 考虑父组的变换
                if obj.parent:
                    parent_transform = obj.parent.transform_matrix
                    # 提取父变换中的旋转部分
                    parent_rotation = parent_transform[:3, :3]
                    # 组合旋转
                    rotation_matrix = parent_rotation @ rotation_matrix
                    # 更新中心位置
                    center = parent_transform @ np.append(obj.position, 1)
                    center = center[:3]
                
                # 根据几何体类型调用相应的交点计算函数
                hit_result = None
                
                if obj.type == GeometryType.BOX:
                    hit_result = self.ray_box_intersection(origin, direction, center, size, rotation_matrix)
                elif obj.type == GeometryType.SPHERE:
                    hit_result = self.ray_sphere_intersection(origin, direction, center, size, rotation_matrix)
                elif obj.type == GeometryType.CYLINDER:
                    hit_result = self.ray_cylinder_intersection(origin, direction, center, size, rotation_matrix)
                elif obj.type == GeometryType.ELLIPSOID:
                    hit_result = self.ray_ellipsoid_intersection(origin, direction, center, size, rotation_matrix)
                elif obj.type == GeometryType.CAPSULE:
                    hit_result = self.ray_capsule_intersection(origin, direction, center, size, rotation_matrix)
                elif obj.type == GeometryType.PLANE:
                    hit_result = self.ray_plane_intersection(origin, direction, center, size, rotation_matrix)
                
                # 检查是否有有效交点，并且是否是最近的
                if hit_result is not None and hit_result[3] > 0 and hit_result[3] < result.distance:
                    result.geometry = obj
                    result.distance = hit_result[3]
                    result.world_position = np.array([hit_result[0], hit_result[1], hit_result[2]])
                    
                    # 计算局部位置（世界坐标转换到局部坐标）
                    local_start, _ = self.transform_ray_to_local(
                        result.world_position, 
                        np.zeros(3),  # 方向无关紧要，因为我们只关心位置转换
                        center, 
                        rotation_matrix
                    )
                    result.local_position = local_start
                    
                    # 设置UV坐标
                    if obj.type == GeometryType.BOX:
                        result.uv_coords = self._compute_box_uv(local_start, size/2.0)
                    elif obj.type == GeometryType.SPHERE:
                        result.uv_coords = self._compute_sphere_uv(local_start)
                    elif obj.type == GeometryType.CYLINDER:
                        result.uv_coords = self._compute_cylinder_uv(local_start, size[0], size[1])
                    elif obj.type == GeometryType.ELLIPSOID:
                        result.uv_coords = self._compute_ellipsoid_uv(local_start, size)
                    elif obj.type == GeometryType.CAPSULE:
                        result.uv_coords = self._compute_capsule_uv(local_start, size[0], size[1])
                    elif obj.type == GeometryType.PLANE:
                        u = (local_start[0] / size[0] + 1.0) / 2.0
                        v = (local_start[1] / size[1] + 1.0) / 2.0
                        result.uv_coords = (u, v)

    def update_camera(self, new_config: Dict) -> None:
        """更新相机配置"""
        self._validate_camera_config(new_config)
        self.camera = new_config

    def _generate_ray(self, screen_pos: Tuple[float, float]) -> Tuple[np.ndarray, np.ndarray]:
        """生成射线（支持透视/正交投影）"""
        vp_w, vp_h = self.camera['viewport']
        ndc_x = (2.0 * screen_pos[0] / vp_w) - 1.0
        ndc_y = 1.0 - (2.0 * screen_pos[1] / vp_h)
        
        if not self.camera['orthographic']:
            # 近平面和远平面上的点
            near_clip = np.array([ndc_x, ndc_y, -1.0, 1.0])
            far_clip = np.array([ndc_x, ndc_y, 1.0, 1.0])
            
            # 变换到世界空间
            inv_projection = np.linalg.inv(self.camera['projection'])
            inv_view = np.linalg.inv(self.camera['view'])
            
            near_eye = inv_projection @ near_clip
            near_eye = near_eye / near_eye[3]  # 齐次坐标归一化
            
            far_eye = inv_projection @ far_clip
            far_eye = far_eye / far_eye[3]  # 齐次坐标归一化
            
            near_world = inv_view @ near_eye
            far_world = inv_view @ far_eye
            
            # 射线方向和起点
            origin = near_world[:3]
            direction = far_world[:3] - near_world[:3]
            direction = direction / np.linalg.norm(direction)
            
            return origin.astype(np.float32), direction.astype(np.float32)

    def _detailed_intersection(self, geo: Geometry, origin: np.ndarray, direction: np.ndarray) -> Optional[RaycastResult]:
        """精确相交检测"""
        inv_matrix = np.linalg.inv(geo.transform_matrix)
        # local_origin = (inv_matrix[:3, :3] @ origin) + inv_matrix[:3, 3]
        origin_homo = np.append(origin, 1.0)
        local_origin = (inv_matrix @ origin_homo)[:3]  # 包含平移分量
        local_dir = inv_matrix[:3, :3] @ direction

        hit = None
        if geo.type == GeometryType.BOX:
            hit = self._ray_box(local_origin, local_dir, geo.size)
        elif geo.type == GeometryType.SPHERE:
            hit = self._ray_sphere(local_origin, local_dir, geo.size[0])  # 假设球体size[0]为半径
        # 可扩展其他几何类型...

        if hit:
            result = RaycastResult()
            result.geometry = geo
            result.distance = hit['distance']
            result.world_position = origin + direction * hit['distance']
            result.local_position = hit['point']
            result.uv_coords = hit.get('uv', (0, 0))
            return result
        return None


    def _compute_box_uv(self, point: np.ndarray, half_size: np.ndarray) -> Tuple[float, float]:
        """立方体UV计算"""
        abs_pt = np.abs(point)
        max_axis = np.argmax(abs_pt)
        face_axes = [(0, 1), (0, 2), (1, 2)][max_axis]
        
        u = (point[face_axes[0]] / half_size[face_axes[0]] + 1) / 2
        v = (point[face_axes[1]] / half_size[face_axes[1]] + 1) / 2
        return (u, v)

    def _compute_sphere_uv(self, point: np.ndarray) -> Tuple[float, float]:
        """球体UV计算（经度/纬度映射）"""
        norm = np.linalg.norm(point)
        if norm == 0:
            return (0, 0)
            
        phi = np.arctan2(point[1], point[0])
        theta = np.arccos(point[2] / norm)
        
        u = (phi + np.pi) / (2 * np.pi)
        v = theta / np.pi
        return (u, v)

    def _get_ortho_width(self) -> float:
        """正交投影宽度计算"""
        return self.camera['viewport'][0] * 0.005 * np.linalg.norm(self.camera['position'])

    def _get_ortho_height(self) -> float:
        """正交投影高度计算"""
        return self.camera['viewport'][1] * 0.005 * np.linalg.norm(self.camera['position'])
    
    def get_transform_matrix(self,geo) -> np.ndarray:
        """生成符合OpenGL标准的TRS矩阵（缩放->旋转->平移）[2,7](@ref)"""
        matrix = np.eye(4)
        
        # 1. 缩放（最先应用）
        scale_matrix = np.diag([*geo.size, 1.0])
        matrix = matrix @ scale_matrix
        
        # 2. 旋转（Z-Y-X欧拉角顺序）
        rx, ry, rz = np.radians(geo.rotation)
        
        # X轴旋转矩阵
        rot_x = np.array([
            [1, 0, 0, 0],
            [0, np.cos(rx), -np.sin(rx), 0],
            [0, np.sin(rx), np.cos(rx), 0],
            [0, 0, 0, 1]
        ])
        
        # Y轴旋转矩阵
        rot_y = np.array([
            [np.cos(ry), 0, np.sin(ry), 0],
            [0, 1, 0, 0],
            [-np.sin(ry), 0, np.cos(ry), 0],
            [0, 0, 0, 1]
        ])
        
        # Z轴旋转矩阵 
        rot_z = np.array([
            [np.cos(rz), -np.sin(rz), 0, 0],
            [np.sin(rz), np.cos(rz), 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])
        
        matrix = matrix @ rot_z @ rot_y @ rot_x  # 顺序Z-Y-X[7](@ref)
        
        # 3. 平移（最后应用）
        matrix[:3, 3] = geo.position
        return matrix
    
    def ray_box_intersection(self, ray_start, ray_direction, center, size, rotation):
        """计算射线与盒子的交点"""
        # 转换射线到盒子的局部坐标系
        local_start, local_direction = self.transform_ray_to_local(ray_start, ray_direction, center, rotation)
        
        hit_result = np.array([0.0, 0.0, 0.0, -1.0])
        
        # 处理局部坐标系中的射线方向为零的情况
        inv_dir = np.zeros(3)
        for i in range(3):
            inv_dir[i] = 1.0 / local_direction[i] if abs(local_direction[i]) > 1e-6 else 1e10
        
        # 设置初始的t范围
        t_min = -1e10
        t_max = 1e10
        
        # 检查所有三个轴
        for i in range(3):
            t1 = (-size[i] - local_start[i]) * inv_dir[i]
            t2 = (size[i] - local_start[i]) * inv_dir[i]
            
            t_min = max(t_min, min(t1, t2))
            t_max = min(t_max, max(t1, t2))
        
        # 如果有有效的交点
        if t_max >= t_min and t_max >= 0:
            t = t_min if t_min >= 0 else t_max
            if t >= 0:
                # 计算局部坐标系中的交点
                local_hit = local_start + t * local_direction
                # 转换回世界坐标系
                world_hit = self.transform_point_to_world(local_hit, center, rotation)
                hit_result = np.array([world_hit[0], world_hit[1], world_hit[2], t])
        
        return hit_result
    
    def transform_ray_to_local(self, ray_start, ray_direction, center, rotation):
        """将射线从世界坐标系转换到物体的局部坐标系"""
        # 先平移射线起点
        local_start = ray_start - center
        
        # 旋转矩阵的转置是其逆（假设正交矩阵）
        rot_transpose = rotation.T
        
        # 应用旋转
        local_start = rot_transpose @ local_start
        local_direction = rot_transpose @ ray_direction
        
        # 确保方向向量保持归一化
        norm = np.linalg.norm(local_direction)
        if norm > 1e-10:  # 添加一个很小的阈值，避免除以接近零的值
            local_direction = local_direction / norm
        else:
            # 如果向量长度太小，使用一个默认方向
            local_direction = np.array([0.0, 0.0, -1.0])
        
        return local_start, local_direction
        
    def transform_point_to_world(self, local_point, center, rotation):
        """将点从局部坐标系转换到世界坐标系"""
        # 应用旋转
        world_point = rotation @ local_point
        # 应用平移
        world_point = world_point + center
        
        return world_point

    def ray_plane_intersection(self, ray_start, ray_direction, center, size, rotation):
        """计算射线与平面的交点"""
        # 转换射线到平面的局部坐标系
        local_start, local_direction = self.transform_ray_to_local(ray_start, ray_direction, center, rotation)
        
        # 在局部坐标系中，平面的法向量是z轴
        normal = np.array([0.0, 0.0, 1.0])
        half_width = size[0]
        half_height = size[1]
        
        hit_result = np.array([0.0, 0.0, 0.0, -1.0])
        denom = np.dot(local_direction, normal)
        
        # 避免除以零，检查光线是否与平面平行
        if abs(denom) > 1e-6:  # 使用更准确的小数值比较
            # 计算平面到射线起点的距离
            t = -local_start[2] / local_direction[2]
            
            # 如果t为正，表示有有效交点
            if t >= 0:
                # 计算交点的局部坐标
                local_hit = local_start + t * local_direction
                
                # 检查交点是否在平面范围内
                if abs(local_hit[0]) <= half_width and abs(local_hit[1]) <= half_height:
                    # 将交点转换回世界坐标系
                    world_hit = self.transform_point_to_world(local_hit, center, rotation)
                    hit_result = np.array([world_hit[0], world_hit[1], world_hit[2], t])
        
        return hit_result

    def ray_sphere_intersection(self, ray_start, ray_direction, center, size, rotation):
        """计算射线与球体的交点"""
        radius = size[0]
        
        hit_result = np.array([0.0, 0.0, 0.0, -1.0])
        
        # 计算向量 (ray_start - center)
        oc = ray_start - center
        
        # 计算二次方程系数
        a = np.dot(ray_direction, ray_direction)
        b = 2.0 * np.dot(oc, ray_direction)
        c = np.dot(oc, oc) - radius * radius
        
        # 计算判别式
        discriminant = b * b - 4 * a * c
        
        # 如果判别式大于等于0，则有解
        if discriminant >= 0:
            # 取较小的非负解作为交点距离
            t1 = (-b - np.sqrt(discriminant)) / (2.0 * a)
            t2 = (-b + np.sqrt(discriminant)) / (2.0 * a)
            
            t = t1 if t1 >= 0 else t2
            
            # 如果t为正，表示有有效交点
            if t >= 0:
                hit_pos = ray_start + t * ray_direction
                hit_result = np.array([hit_pos[0], hit_pos[1], hit_pos[2], t])
        
        return hit_result

    def ray_cylinder_intersection(self, ray_start, ray_direction, center, size, rotation):
        """计算射线与圆柱体的交点"""
        # 转换射线到圆柱体的局部坐标系
        local_start, local_direction = self.transform_ray_to_local(ray_start, ray_direction, center, rotation)
        
        radius = size[0]
        half_height = size[1]
        
        hit_result = np.array([0.0, 0.0, 0.0, -1.0])
        
        # 检查与无限长圆柱的相交，圆柱轴为z轴
        # 仅考虑xy平面上的方向分量
        a = local_direction[0]**2 + local_direction[1]**2
        
        # 如果a很小，射线几乎与z轴平行
        if a < 1e-6:
            # 检查xy平面中的射线位置是否在圆内
            if local_start[0]**2 + local_start[1]**2 <= radius**2:
                # 计算与上下底面的交点
                if abs(local_direction[2]) > 1e-6:
                    t1 = (half_height - local_start[2]) / local_direction[2]
                    t2 = (-half_height - local_start[2]) / local_direction[2]
                    
                    t = -1.0
                    if t1 >= 0 and (t < 0 or t1 < t):
                        t = t1
                    if t2 >= 0 and (t < 0 or t2 < t):
                        t = t2
                    
                    if t >= 0:
                        local_hit = local_start + t * local_direction
                        world_hit = self.transform_point_to_world(local_hit, center, rotation)
                        hit_result = np.array([world_hit[0], world_hit[1], world_hit[2], t])
        else:
            # 计算标准圆柱体检测
            b = 2.0 * (local_start[0] * local_direction[0] + local_start[1] * local_direction[1])
            c = local_start[0]**2 + local_start[1]**2 - radius**2
            
            discriminant = b**2 - 4*a*c
            
            if discriminant >= 0:
                t1 = (-b - np.sqrt(discriminant)) / (2*a)
                t2 = (-b + np.sqrt(discriminant)) / (2*a)
                
                # 找到最小的非负t值
                t = -1.0
                if t1 >= 0:
                    t = t1
                elif t2 >= 0:
                    t = t2
                    
                if t >= 0:
                    # 计算交点
                    local_hit = local_start + t * local_direction
                    
                    # 检查交点是否在圆柱体高度范围内
                    if abs(local_hit[2]) <= half_height:
                        world_hit = self.transform_point_to_world(local_hit, center, rotation)
                        hit_result = np.array([world_hit[0], world_hit[1], world_hit[2], t])
                    else:
                        # 检查与端盖平面的交点
                        cap_z = half_height if local_hit[2] > 0 else -half_height
                        if abs(local_direction[2]) > 1e-6:
                            cap_t = (cap_z - local_start[2]) / local_direction[2]
                            if cap_t >= 0:
                                cap_hit = local_start + cap_t * local_direction
                                if cap_hit[0]**2 + cap_hit[1]**2 <= radius**2:
                                    world_hit = self.transform_point_to_world(cap_hit, center, rotation)
                                    hit_result = np.array([world_hit[0], world_hit[1], world_hit[2], cap_t])
    
        return hit_result

    def ray_ellipsoid_intersection(self, ray_start, ray_direction, center, size, rotation):
        """计算射线与椭球体的交点"""
        # 转换射线到椭球体的局部坐标系
        local_start, local_direction = self.transform_ray_to_local(ray_start, ray_direction, center, rotation)
        
        hit_result = np.array([0.0, 0.0, 0.0, -1.0])
        
        # 将问题转换为单位球相交，通过缩放空间
        inv_size = np.array([1.0/size[0], 1.0/size[1], 1.0/size[2]])
        
        # 缩放局部坐标系中的射线
        scaled_start = local_start * inv_size
        scaled_dir = local_direction * inv_size
        
        # 重新归一化方向向量
        scaled_dir_norm = np.linalg.norm(scaled_dir)
        if scaled_dir_norm > 1e-6:  # 避免除以零
            scaled_dir = scaled_dir / scaled_dir_norm
        
        # 执行标准球体相交测试
        a = np.dot(scaled_dir, scaled_dir)
        b = 2.0 * np.dot(scaled_start, scaled_dir)
        c = np.dot(scaled_start, scaled_start) - 1.0  # 单位球半径为1
        
        discriminant = b * b - 4 * a * c
        
        if discriminant >= 0:
            # 计算两个可能的交点
            t1 = (-b - np.sqrt(discriminant)) / (2.0 * a)
            t2 = (-b + np.sqrt(discriminant)) / (2.0 * a)
            
            # 选择最近的非负交点
            t = -1.0
            if t1 >= 0:
                t = t1
            elif t2 >= 0:
                t = t2
            
            # 如果t为正，表示有有效交点
            if t >= 0:
                # 计算缩放空间中的交点，然后转回原始空间
                local_hit = local_start + t * local_direction
                world_hit = self.transform_point_to_world(local_hit, center, rotation)
                hit_result = np.array([world_hit[0], world_hit[1], world_hit[2], t])
        
        return hit_result

    def ray_capsule_intersection(self, ray_start, ray_direction, center, size, rotation):
        """计算射线与胶囊体的交点"""
        # 转换射线到胶囊体的局部坐标系
        local_start, local_direction = self.transform_ray_to_local(ray_start, ray_direction, center, rotation)
        
        radius = size[0]  # 半径
        half_height = size[1]  # 圆柱体部分的半高度
        
        hit_result = np.array([0.0, 0.0, 0.0, -1.0])
        min_t = float('inf')
        has_hit = False
        
        # 1. 检查与圆柱体部分的交点
        a = local_direction[0]**2 + local_direction[1]**2
        
        if a > 1e-6:
            b = 2.0 * (local_start[0] * local_direction[0] + local_start[1] * local_direction[1])
            c = local_start[0]**2 + local_start[1]**2 - radius**2
            
            discriminant = b**2 - 4*a*c
            
            if discriminant >= 0:
                t1 = (-b - np.sqrt(discriminant)) / (2*a)
                t2 = (-b + np.sqrt(discriminant)) / (2*a)
                
                # 找到有效的t值
                for t in (t1, t2):
                    if t >= 0:
                        hit_point = local_start + t * local_direction
                        # 检查是否在圆柱体高度范围内
                        if abs(hit_point[2]) <= half_height and t < min_t:
                            min_t = t
                            local_hit = hit_point
                            world_hit = self.transform_point_to_world(local_hit, center, rotation)
                            hit_result = np.array([world_hit[0], world_hit[1], world_hit[2], t])
                            has_hit = True
        
        # 2. 检查与上半球的交点
        sphere1_center = np.array([0.0, 0.0, half_height])
        oc1 = local_start - sphere1_center
        
        a = np.dot(local_direction, local_direction)
        b = 2.0 * np.dot(oc1, local_direction)
        c = np.dot(oc1, oc1) - radius**2
        
        discriminant = b**2 - 4*a*c
        
        if discriminant >= 0:
            t1 = (-b - np.sqrt(discriminant)) / (2*a)
            t2 = (-b + np.sqrt(discriminant)) / (2*a)
            
            for t in (t1, t2):
                if t >= 0 and t < min_t:
                    # 确保交点在半球的正确部分
                    hit_point = local_start + t * local_direction
                    local_z = hit_point[2] - sphere1_center[2]
                    if local_z >= 0:  # 只考虑上半球的上半部分
                        min_t = t
                        local_hit = hit_point
                        world_hit = self.transform_point_to_world(local_hit, center, rotation)
                        hit_result = np.array([world_hit[0], world_hit[1], world_hit[2], t])
                        has_hit = True
        
        # 3. 检查与下半球的交点
        sphere2_center = np.array([0.0, 0.0, -half_height])
        oc2 = local_start - sphere2_center
        
        a = np.dot(local_direction, local_direction)
        b = 2.0 * np.dot(oc2, local_direction)
        c = np.dot(oc2, oc2) - radius**2
        
        discriminant = b**2 - 4*a*c
        
        if discriminant >= 0:
            t1 = (-b - np.sqrt(discriminant)) / (2*a)
            t2 = (-b + np.sqrt(discriminant)) / (2*a)
            
            for t in (t1, t2):
                if t >= 0 and t < min_t:
                    # 确保交点在半球的正确部分
                    hit_point = local_start + t * local_direction
                    local_z = hit_point[2] - sphere2_center[2]
                    if local_z <= 0:  # 只考虑下半球的下半部分
                        min_t = t
                        local_hit = hit_point
                        world_hit = self.transform_point_to_world(local_hit, center, rotation)
                        hit_result = np.array([world_hit[0], world_hit[1], world_hit[2], t])
                        has_hit = True
        
        # 如果没有任何交点，结果中的t值保持为-1
        if not has_hit:
            hit_result[3] = -1.0
        
        return hit_result

    def _compute_cylinder_uv(self, local_point, radius, half_height):
        """计算圆柱体的UV坐标"""
        # 计算圆柱体侧面的UV坐标：u基于角度，v基于高度
        local_xy = np.array([local_point[0], local_point[1]])
        norm_xy = np.linalg.norm(local_xy)
        
        # 确定是侧面还是顶部/底部的交点
        if abs(local_point[2]) >= half_height - 1e-4:
            # 顶部或底部平面的UV
            u = (local_point[0] / radius + 1.0) / 2.0
            v = (local_point[1] / radius + 1.0) / 2.0
        else:
            # 侧面的UV
            phi = np.arctan2(local_point[1], local_point[0])
            u = (phi + np.pi) / (2 * np.pi)
            v = (local_point[2] + half_height) / (2 * half_height)
        
        return (u, v)

    def _compute_capsule_uv(self, local_point, radius, half_height):
        """计算胶囊体的UV坐标"""
        # 确定交点是在半球上还是在圆柱部分
        if local_point[2] > half_height:
            # 上半球
            sphere_center = np.array([0.0, 0.0, half_height])
            local_sphere_point = local_point - sphere_center
            normal = local_sphere_point / np.linalg.norm(local_sphere_point)
            phi = np.arctan2(normal[1], normal[0])
            theta = np.arccos(normal[2])
            u = (phi + np.pi) / (2 * np.pi)
            v = 1.0 - theta / np.pi
        elif local_point[2] < -half_height:
            # 下半球
            sphere_center = np.array([0.0, 0.0, -half_height])
            local_sphere_point = local_point - sphere_center
            normal = local_sphere_point / np.linalg.norm(local_sphere_point)
            phi = np.arctan2(normal[1], normal[0])
            theta = np.arccos(-normal[2])  # 注意这里是-normal[2]
            u = (phi + np.pi) / (2 * np.pi)
            v = theta / np.pi
        else:
            # 圆柱部分
            phi = np.arctan2(local_point[1], local_point[0])
            u = (phi + np.pi) / (2 * np.pi)
            v = (local_point[2] + half_height) / (2 * half_height)
        
        return (u, v)

    def _compute_ellipsoid_uv(self, local_point, size):
        """计算椭球体的UV坐标"""
        # 缩放点回到单位球，然后用球面坐标计算UV
        scaled_point = local_point / size
        normal = scaled_point / np.linalg.norm(scaled_point)
        
        phi = np.arctan2(normal[1], normal[0])
        theta = np.arccos(normal[2])
        
        u = (phi + np.pi) / (2 * np.pi)
        v = theta / np.pi
        
        return (u, v)