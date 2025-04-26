"""
光线投射器

用于在3D场景中进行物体选择的射线投射器实现。
"""

import numpy as np
from typing import List, Optional, Tuple, Dict
from .geometry import BaseGeometry, GeometryGroup

class RaycastResult:
    """
    射线投射结果类
    
    存储射线投射的结果信息
    """
    def __init__(self, geometry=None, distance=float('inf'), hit_point=None, normal=None):
        self.geometry = geometry  # 命中的几何体
        self.distance = distance  # 射线起点到命中点的距离
        self.hit_point = np.zeros(3) if hit_point is None else hit_point  # 世界坐标系中的命中点
        self.normal = np.zeros(3) if normal is None else normal  # 命中点的法线方向
    
    def is_hit(self):
        """是否命中了几何体"""
        return self.geometry is not None and self.distance < float('inf')


class GeometryRaycaster:
    """
    几何体射线投射器
    
    用于从摄像机位置投射射线，检测与场景中几何体的相交
    """
    def __init__(self, camera_config, geometries):
        """
        初始化射线投射器
        
        参数:
            camera_config: 摄像机配置，包含位置、方向等信息
            geometries: 场景中的几何体列表
        """
        self.camera_config = camera_config
        self.geometries = geometries
    
    def update_camera(self, camera_config):
        """更新摄像机配置"""
        self.camera_config = camera_config
    
    def update_geometries(self, geometries):
        """更新场景几何体"""
        self.geometries = geometries
    
    def raycast(self, screen_x, screen_y, viewport_width, viewport_height) -> RaycastResult:
        """
        从屏幕坐标投射射线，返回命中结果
        
        参数:
            screen_x: 屏幕X坐标
            screen_y: 屏幕Y坐标
            viewport_width: 视口宽度
            viewport_height: 视口高度
            
        返回:
            RaycastResult 对象，包含命中信息
        """
        # 1. 计算射线起点和方向
        ray_origin, ray_direction = self._screen_to_ray(screen_x, screen_y, viewport_width, viewport_height)
        
        # 2. 对所有几何体进行测试
        result = self._intersect_geometries(ray_origin, ray_direction)
        
        return result
    
    def _screen_to_ray(self, screen_x, screen_y, viewport_width, viewport_height) -> Tuple[np.ndarray, np.ndarray]:
        """
        将屏幕坐标转换为射线
        
        参数:
            screen_x: 屏幕X坐标
            screen_y: 屏幕Y坐标
            viewport_width: 视口宽度
            viewport_height: 视口高度
            
        返回:
            tuple: (射线起点, 射线方向)
        """
        # 1. 将屏幕坐标归一化到[-1, 1]范围
        x = 2.0 * screen_x / viewport_width - 1.0
        y = 1.0 - 2.0 * screen_y / viewport_height  # OpenGL坐标系Y轴向上
        
        # 2. 创建NDC（归一化设备坐标）空间中的点
        ndc_near = np.array([x, y, -1.0, 1.0])  # 近平面点
        ndc_far = np.array([x, y, 1.0, 1.0])    # 远平面点
        
        # 3. 使用逆投影矩阵将点变换到视图空间
        inv_projection = np.linalg.inv(self.camera_config['projection_matrix'])
        view_near = inv_projection @ ndc_near
        view_far = inv_projection @ ndc_far
        
        # 归一化w分量
        view_near /= view_near[3]
        view_far /= view_far[3]
        
        # 4. 使用逆视图矩阵将点变换到世界空间
        inv_view = np.linalg.inv(self.camera_config['view_matrix'])
        world_near = inv_view @ view_near
        world_far = inv_view @ view_far
        
        # 5. 计算射线方向和原点
        ray_origin = world_near[:3]
        ray_direction = world_far[:3] - ray_origin
        ray_direction = ray_direction / np.linalg.norm(ray_direction)  # 归一化方向向量
        
        return ray_origin, ray_direction
    
    def _intersect_geometries(self, ray_origin, ray_direction) -> RaycastResult:
        """
        测试射线与场景中所有几何体的相交
        
        参数:
            ray_origin: 射线起点
            ray_direction: 射线方向
            
        返回:
            RaycastResult: 最近的命中结果
        """
        closest_result = RaycastResult()  # 默认未命中
        
        # 递归处理所有几何体（包括组中的子对象）
        all_geometries = self._collect_all_geometries(self.geometries)
        
        for geo in all_geometries:
            # 只测试实际几何体，不测试组，并且跳过被选中的对象（如果在操作模式下）
            if (hasattr(geo, 'type') and geo.type != 'group' and not (hasattr(geo, 'selected') and geo.selected)):
                result = self._intersect_geometry(geo, ray_origin, ray_direction)
                if result.is_hit() and result.distance < closest_result.distance:
                    closest_result = result
        
        return closest_result
    
    def _collect_all_geometries(self, geometries) -> List[BaseGeometry]:
        """
        收集场景中的所有几何体（包括层级结构中的子对象）
        
        参数:
            geometries: 几何体列表或单个几何体
            
        返回:
            List[BaseGeometry]: 场景中的所有几何体
        """
        result = []
        
        if isinstance(geometries, list):
            for geo in geometries:
                result.extend(self._collect_all_geometries(geo))
        else:
            # 单个几何体
            result.append(geometries)
            
            # 如果是组，添加其所有子对象
            if hasattr(geometries, 'children'):
                for child in geometries.children:
                    result.extend(self._collect_all_geometries(child))
        
        return result
    
    def _intersect_geometry(self, geometry, ray_origin, ray_direction) -> RaycastResult:
        """
        测试射线与单个几何体的相交
        
        参数:
            geometry: 要测试的几何体
            ray_origin: 射线起点
            ray_direction: 射线方向
            
        返回:
            RaycastResult: 命中结果
        """
        # 检查是否是控制器几何体（可以通过tag识别）
        is_controller = hasattr(geometry, 'tag') and geometry.tag in ['x_axis', 'y_axis', 'z_axis']
        
        # 检查是否是旋转控制器
        is_rotation_controller = hasattr(geometry, 'tag') and 'rotation' in getattr(geometry, 'tag', '')
        
        # 基于几何体类型进行不同的相交测试
        if geometry.type == 'box' or (is_controller and hasattr(geometry, 'type') and geometry.type == 'box'):
            return self._intersect_box(geometry, ray_origin, ray_direction)
        elif (is_rotation_controller and geometry.type == 'cylinder') or geometry.type == 'cylinder':
            return self._intersect_cylinder(geometry, ray_origin, ray_direction)
        elif (is_rotation_controller and geometry.type == 'torus'):
            # 对于环形旋转控制器，可以使用特殊的相交检测方法
            return self._intersect_rotation_ring(geometry, ray_origin, ray_direction)
        elif geometry.type == 'sphere':
            return self._intersect_sphere(geometry, ray_origin, ray_direction)
        elif geometry.type == 'capsule':
            return self._intersect_capsule(geometry, ray_origin, ray_direction)
        elif geometry.type == 'ellipsoid':
            return self._intersect_ellipsoid(geometry, ray_origin, ray_direction)
        elif geometry.type == 'plane':
            return self._intersect_plane(geometry, ray_origin, ray_direction)
        else:
            # 默认使用AABB（轴对齐包围盒）检测
            return self._intersect_aabb(geometry, ray_origin, ray_direction)
    
    def _intersect_box(self, geometry, ray_origin, ray_direction) -> RaycastResult:
        """盒子碰撞检测"""
        # 从世界坐标系获取几何体数据
        center = geometry.get_world_position()
        size = geometry.size
        
        # 获取旋转矩阵
        rotation_matrix = geometry.transform_matrix[:3, :3]
        if geometry.parent:
            parent_transform = geometry.parent.transform_matrix
            # 提取父变换中的旋转部分
            parent_rotation = parent_transform[:3, :3]
            # 组合旋转
            rotation_matrix = parent_rotation @ rotation_matrix                    # 更新中心位置
            center = parent_transform @ np.append(geometry.position, 1)
            center = center[:3]
        
        # 转换射线到盒子的局部坐标系
        local_start, local_direction = self.transform_ray_to_local(ray_origin, ray_direction, center, rotation_matrix)
        
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
                world_hit = self.transform_point_to_world(local_hit, center, rotation_matrix)
                
                # 计算法线
                local_normal = np.zeros(3)
                for i in range(3):
                    if abs(local_hit[i] - (-size[i])) < 1e-5:
                        local_normal[i] = -1
                        break
                    elif abs(local_hit[i] - size[i]) < 1e-5:
                        local_normal[i] = 1
                        break
                    
                world_normal = rotation_matrix @ local_normal
                world_normal = world_normal / np.linalg.norm(world_normal) if np.linalg.norm(world_normal) > 0 else np.array([0, 1, 0])
                
                return RaycastResult(geometry, t, world_hit, world_normal)
        
        return RaycastResult()  # 未命中
    
    def _intersect_sphere(self, geometry, ray_origin, ray_direction) -> RaycastResult:
        """球体碰撞检测"""
        # 从世界坐标系获取几何体数据
        center = geometry.get_world_position()
        size = geometry.size
        
        # 获取旋转矩阵
        rotation_matrix = geometry.transform_matrix[:3, :3]
        if geometry.parent:
            parent_transform = geometry.parent.transform_matrix
            # 提取父变换中的旋转部分
            parent_rotation = parent_transform[:3, :3]
            # 组合旋转
            rotation_matrix = parent_rotation @ rotation_matrix                    # 更新中心位置
            center = parent_transform @ np.append(geometry.position, 1)
            center = center[:3]
        # 球心在世界坐标系中的位置

        radius = size[0]
        
        hit_result = np.array([0.0, 0.0, 0.0, -1.0])
        
        # 计算向量 (ray_start - center)
        oc = ray_origin - center
        
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
                hit_pos = ray_origin + t * ray_direction
                
                # 计算法线
                normal = hit_pos - center
                normal = normal / np.linalg.norm(normal)
                
                return RaycastResult(geometry, t, hit_pos, normal)
        
        return RaycastResult()  # 未命中
    
    def _intersect_cylinder(self, geometry, ray_origin, ray_direction) -> RaycastResult:
        """圆柱体碰撞检测"""
        # 从世界坐标系获取几何体数据

        center = geometry.get_world_position()
        size = geometry.size
        
        # 获取旋转矩阵
        rotation_matrix = geometry.transform_matrix[:3, :3]
        if geometry.parent:
            parent_transform = geometry.parent.transform_matrix
            # 提取父变换中的旋转部分
            parent_rotation = parent_transform[:3, :3]
            # 组合旋转
            rotation_matrix = parent_rotation @ rotation_matrix                    # 更新中心位置
            center = parent_transform @ np.append(geometry.position, 1)
            center = center[:3]
        
        # 检查是否是旋转控制器
        is_rotation_controller = hasattr(geometry, 'tag') and 'rotation' in getattr(geometry, 'tag', '')
        
        # 如果是旋转控制器，可以调整碰撞检测的精度或行为
        if is_rotation_controller:
            # 可以调整大小以增加选择区域，或者修改其他参数
            # 例如，扩大半径使控制器更容易被选中
            radius = size[0] * 1.2  # 增加20%的选择区域
            half_height = size[1]
        else:
            radius = size[0]
            half_height = size[1]
        
        # 转换射线到圆柱体的局部坐标系
        local_start, local_direction = self.transform_ray_to_local(ray_origin, ray_direction, center, rotation_matrix)
        
        # 检查与无限长圆柱的相交，圆柱轴为y轴
        # 仅考虑xz平面上的方向分量
        a = local_direction[0]**2 + local_direction[2]**2
        
        # 如果a很小，射线几乎与y轴平行
        if a < 1e-6:
            # 检查xz平面中的射线位置是否在圆内
            if local_start[0]**2 + local_start[2]**2 <= radius**2:
                # 计算与上下底面的交点
                if abs(local_direction[1]) > 1e-6:
                    t1 = (half_height - local_start[1]) / local_direction[1]
                    t2 = (-half_height - local_start[1]) / local_direction[1]
                    
                    t = -1.0
                    if t1 >= 0 and (t < 0 or t1 < t):
                        t = t1
                    if t2 >= 0 and (t < 0 or t2 < t):
                        t = t2
                    
                    if t >= 0:
                        local_hit = local_start + t * local_direction
                        world_hit = self.transform_point_to_world(local_hit, center, rotation_matrix)
                        
                        # 法线指向y轴的正向或负向
                        local_normal = np.array([0, 1, 0]) if local_hit[1] > 0 else np.array([0, -1, 0])
                        world_normal = rotation_matrix @ local_normal
                        world_normal = world_normal / np.linalg.norm(world_normal)
                        
                        return RaycastResult(geometry, t, world_hit, world_normal)
            
            return RaycastResult()  # 未命中
        else:
            # 计算标准圆柱体检测
            b = 2.0 * (local_start[0] * local_direction[0] + local_start[2] * local_direction[2])
            c = local_start[0]**2 + local_start[2]**2 - radius**2
            
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
                    if abs(local_hit[1]) <= half_height:
                        world_hit = self.transform_point_to_world(local_hit, center, rotation_matrix)
                        
                        # 法线指向从轴到表面点的方向
                        local_normal = np.array([local_hit[0], 0, local_hit[2]])
                        local_normal = local_normal / np.linalg.norm(local_normal)
                        world_normal = rotation_matrix @ local_normal
                        world_normal = world_normal / np.linalg.norm(world_normal)
                        
                        return RaycastResult(geometry, t, world_hit, world_normal)
                    else:
                        # 检查与端盖平面的交点
                        cap_y = half_height if local_hit[1] > 0 else -half_height
                        if abs(local_direction[1]) > 1e-6:
                            cap_t = (cap_y - local_start[1]) / local_direction[1]
                            if cap_t >= 0:
                                cap_hit = local_start + cap_t * local_direction
                                if cap_hit[0]**2 + cap_hit[2]**2 <= radius**2:
                                    world_hit = self.transform_point_to_world(cap_hit, center, rotation_matrix)
                                    
                                    # 法线指向y轴的正向或负向
                                    local_normal = np.array([0, 1, 0]) if cap_y > 0 else np.array([0, -1, 0])
                                    world_normal = rotation_matrix @ local_normal
                                    world_normal = world_normal / np.linalg.norm(world_normal)
                                    
                                    return RaycastResult(geometry, cap_t, world_hit, world_normal)
        
        return RaycastResult()  # 未命中
    
    def _intersect_plane(self, geometry, ray_origin, ray_direction) -> RaycastResult:
        """平面碰撞检测"""
        # 从世界坐标系获取几何体数据
        # 从世界坐标系获取几何体数据
        center = geometry.get_world_position()
        size = geometry.size
        
        # 获取旋转矩阵
        rotation_matrix = geometry.transform_matrix[:3, :3]
        if geometry.parent:
            parent_transform = geometry.parent.transform_matrix
            # 提取父变换中的旋转部分
            parent_rotation = parent_transform[:3, :3]
            # 组合旋转
            rotation_matrix = parent_rotation @ rotation_matrix                    # 更新中心位置
            center = parent_transform @ np.append(geometry.position, 1)
            center = center[:3]
        # 转换射线到平面的局部坐标系
        local_start, local_direction = self.transform_ray_to_local(ray_origin, ray_direction, center, rotation_matrix)
        
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
                    world_hit = self.transform_point_to_world(local_hit, center, rotation_matrix)
                    
                    # 将法线转换到世界坐标系
                    world_normal = rotation_matrix @ normal
                    world_normal = world_normal / np.linalg.norm(world_normal)
                    
                    return RaycastResult(geometry, t, world_hit, world_normal)
        
        return RaycastResult()  # 未命中或平行
    
    def _intersect_ellipsoid(self, geometry, ray_origin, ray_direction) -> RaycastResult:
        """椭球体碰撞检测"""
        # 从世界坐标系获取几何体数据
        # 从世界坐标系获取几何体数据
        center = geometry.get_world_position()
        size = geometry.size
        
        # 获取旋转矩阵
        rotation_matrix = geometry.transform_matrix[:3, :3]
        if geometry.parent:
            parent_transform = geometry.parent.transform_matrix
            # 提取父变换中的旋转部分
            parent_rotation = parent_transform[:3, :3]
            # 组合旋转
            rotation_matrix = parent_rotation @ rotation_matrix                    # 更新中心位置
            center = parent_transform @ np.append(geometry.position, 1)
            center = center[:3]
        
        # 转换射线到椭球体的局部坐标系
        local_start, local_direction = self.transform_ray_to_local(ray_origin, ray_direction, center, rotation_matrix)
        
        # 将问题转换为单位球相交，通过缩放空间
        inv_size = np.array([1.0/size[0], 1.0/size[1], 1.0/size[2]])
        
        # 缩放局部坐标系中的射线
        scaled_start = local_start * inv_size
        scaled_dir = local_direction * inv_size
        
        # 重新归一化方向向量
        scaled_dir_norm = np.linalg.norm(scaled_dir)
        if scaled_dir_norm > 1e-6:  # 避免除以零
            scaled_dir = scaled_dir / scaled_dir_norm
        else:
            return RaycastResult()  # 无效方向向量
        
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
                scaled_hit = scaled_start + t * scaled_dir
                local_hit = scaled_hit / inv_size
                world_hit = self.transform_point_to_world(local_hit, center, rotation_matrix)
                
                # 计算法线（椭球体表面法线需要特殊处理）
                # 法线与梯度成比例：grad(x²/a² + y²/b² + z²/c² - 1) = (2x/a², 2y/b², 2z/c²)
                local_normal = np.array([
                    2 * scaled_hit[0],
                    2 * scaled_hit[1],
                    2 * scaled_hit[2]
                ])
                local_normal = local_normal / np.linalg.norm(local_normal)
                world_normal = rotation_matrix @ local_normal
                world_normal = world_normal / np.linalg.norm(world_normal)
                
                return RaycastResult(geometry, t, world_hit, world_normal)
        
        return RaycastResult()  # 未命中
    
    def _intersect_aabb(self, geometry, ray_origin, ray_direction) -> RaycastResult:
        """AABB（轴对齐包围盒）碰撞检测"""
        # 获取几何体的AABB
        aabb_min = geometry.aabb_min
        aabb_max = geometry.aabb_max
        
        # 避免除以零
        inv_dir = 1.0 / (ray_direction + 1e-10)
        
        # 计算与AABB的交点
        t1 = (aabb_min - ray_origin) * inv_dir
        t2 = (aabb_max - ray_origin) * inv_dir
        
        t_min = np.max(np.minimum(t1, t2))
        t_max = np.min(np.maximum(t1, t2))
        
        if t_max < 0 or t_min > t_max:
            return RaycastResult()  # 未命中
        
        # 计算交点
        t = t_min if t_min > 0 else t_max
        hit_point = ray_origin + t * ray_direction
        
        # 简化的法线计算
        normal = np.zeros(3)
        for i in range(3):
            if abs(hit_point[i] - aabb_min[i]) < 1e-5:
                normal[i] = -1
                break
            elif abs(hit_point[i] - aabb_max[i]) < 1e-5:
                normal[i] = 1
                break
        
        # 如果没有找到法线，使用射线方向的反方向
        if np.all(normal == 0):
            normal = -ray_direction
        
        normal = normal / np.linalg.norm(normal)
        
        return RaycastResult(geometry, t, hit_point, normal)
    
    def _intersect_capsule(self, geometry, ray_origin, ray_direction) -> RaycastResult:
        """胶囊体碰撞检测"""
        # 从世界坐标系获取几何体数据
        # 从世界坐标系获取几何体数据
        center = geometry.get_world_position()
        size = geometry.size
        
        # 获取旋转矩阵
        rotation_matrix = geometry.transform_matrix[:3, :3]
        if geometry.parent:
            parent_transform = geometry.parent.transform_matrix
            # 提取父变换中的旋转部分
            parent_rotation = parent_transform[:3, :3]
            # 组合旋转
            rotation_matrix = parent_rotation @ rotation_matrix                    # 更新中心位置
            center = parent_transform @ np.append(geometry.position, 1)
            center = center[:3]
        
        # 转换射线到胶囊体的局部坐标系
        local_start, local_direction = self.transform_ray_to_local(ray_origin, ray_direction, center, rotation_matrix)
        
        radius = size[0]  # 半径
        half_height = size[1]  # 圆柱体部分的半高度
        
        min_t = float('inf')
        has_hit = False
        local_hit = None
        local_normal = None
        
        # 1. 检查与圆柱体部分的交点
        a = local_direction[0]**2 + local_direction[2]**2
        
        if a > 1e-6:
            b = 2.0 * (local_start[0] * local_direction[0] + local_start[2] * local_direction[2])
            c = local_start[0]**2 + local_start[2]**2 - radius**2
            
            discriminant = b**2 - 4*a*c
            
            if discriminant >= 0:
                t1 = (-b - np.sqrt(discriminant)) / (2*a)
                t2 = (-b + np.sqrt(discriminant)) / (2*a)
                
                # 找到有效的t值
                for t in (t1, t2):
                    if t >= 0:
                        hit_point = local_start + t * local_direction
                        # 检查是否在圆柱体高度范围内
                        if abs(hit_point[1]) <= half_height and t < min_t:
                            min_t = t
                            local_hit = hit_point
                            local_normal = np.array([local_hit[0], 0, local_hit[2]])
                            local_normal = local_normal / np.linalg.norm(local_normal)
                            has_hit = True
        
        # 2. 检查与上半球的交点
        sphere1_center = np.array([0.0, half_height, 0.0])
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
                    local_y = hit_point[1] - sphere1_center[1]
                    if local_y >= 0:  # 只考虑上半球的上半部分
                        min_t = t
                        local_hit = hit_point
                        local_normal = local_hit - sphere1_center
                        local_normal = local_normal / np.linalg.norm(local_normal)
                        has_hit = True
        
        # 3. 检查与下半球的交点
        sphere2_center = np.array([0.0, -half_height, 0.0])
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
                    local_y = hit_point[1] - sphere2_center[1]
                    if local_y <= 0:  # 只考虑下半球的下半部分
                        min_t = t
                        local_hit = hit_point
                        local_normal = local_hit - sphere2_center
                        local_normal = local_normal / np.linalg.norm(local_normal)
                        has_hit = True
        
        # 如果有交点，返回结果
        if has_hit:
            world_hit = self.transform_point_to_world(local_hit, center, rotation_matrix)
            world_normal = rotation_matrix @ local_normal
            world_normal = world_normal / np.linalg.norm(world_normal)
            
            return RaycastResult(geometry, min_t, world_hit, world_normal)
        
        return RaycastResult()  # 未命中
    
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
    
    def _intersect_rotation_ring(self, geometry, ray_origin, ray_direction) -> RaycastResult:
        """环形旋转控制器碰撞检测"""
        # 从世界坐标系获取几何体数据
        # 从世界坐标系获取几何体数据
        center = geometry.get_world_position()
        size = geometry.size
        
        # 获取旋转矩阵
        rotation_matrix = geometry.transform_matrix[:3, :3]
        if geometry.parent:
            parent_transform = geometry.parent.transform_matrix
            # 提取父变换中的旋转部分
            parent_rotation = parent_transform[:3, :3]
            # 组合旋转
            rotation_matrix = parent_rotation @ rotation_matrix                    # 更新中心位置
            center = parent_transform @ np.append(geometry.position, 1)
            center = center[:3]
        
        # 转换射线到环的局部坐标系
        local_start, local_direction = self.transform_ray_to_local(ray_origin, ray_direction, center, rotation_matrix)
        
        # 获取环的几何参数
        major_radius = size[0]  # 环的主半径
        minor_radius = size[1]  # 环的次半径（管道粗细）
        # 可以忽略 size[2]，或者将其用作其他目的
        
        # 根据控制器标签确定环所在的平面
        tag = getattr(geometry, 'tag', '')
        
        # 确定环的法线方向
        normal = np.array([0.0, 0.0, 0.0])
        if 'x_rotation' in tag:
            normal = np.array([1.0, 0.0, 0.0])  # X轴旋转环在YZ平面
        elif 'y_rotation' in tag:
            normal = np.array([0.0, 1.0, 0.0])  # Y轴旋转环在XZ平面
        elif 'z_rotation' in tag:
            normal = np.array([0.0, 0.0, 1.0])  # Z轴旋转环在XY平面
        
        # 计算射线与平面的交点
        denom = np.dot(normal, local_direction)
        
        # 如果射线几乎平行于平面，则没有交点
        if abs(denom) < 1e-6:
            return RaycastResult()
        
        # 计算射线到平面的参数t
        t = -np.dot(local_start, normal) / denom
        
        # 如果t为负值，则交点在射线的反方向
        if t < 0:
            return RaycastResult()
        
        # 计算交点
        intersection = local_start + t * local_direction
        
        # 计算交点到环中心的距离
        if 'x_rotation' in tag:
            # 在YZ平面上计算
            distance_to_center = np.sqrt(intersection[1]**2 + intersection[2]**2)
        elif 'y_rotation' in tag:
            # 在XZ平面上计算
            distance_to_center = np.sqrt(intersection[0]**2 + intersection[2]**2)
        elif 'z_rotation' in tag:
            # 在XY平面上计算
            distance_to_center = np.sqrt(intersection[0]**2 + intersection[1]**2)
        else:
            return RaycastResult()  # 无法确定平面
        
        # 检查距离是否在环的有效范围内（主半径 +/- 次半径）
        if abs(distance_to_center - major_radius) <= minor_radius:
            # 命中了环
            # 计算世界坐标系中的交点
            world_hit = self.transform_point_to_world(intersection, center, rotation_matrix)
            
            # 计算法线
            # 对于环形，法线方向是从环的中心轴到交点的方向
            local_normal = np.array([0.0, 0.0, 0.0])
            
            if 'x_rotation' in tag:
                # 计算YZ平面上的单位向量
                if distance_to_center > 0:
                    local_normal = np.array([0.0, intersection[1], intersection[2]]) / distance_to_center
                else:
                    local_normal = np.array([0.0, 1.0, 0.0])  # 默认值
            elif 'y_rotation' in tag:
                # 计算XZ平面上的单位向量
                if distance_to_center > 0:
                    local_normal = np.array([intersection[0], 0.0, intersection[2]]) / distance_to_center
                else:
                    local_normal = np.array([1.0, 0.0, 0.0])  # 默认值
            elif 'z_rotation' in tag:
                # 计算XY平面上的单位向量
                if distance_to_center > 0:
                    local_normal = np.array([intersection[0], intersection[1], 0.0]) / distance_to_center
                else:
                    local_normal = np.array([1.0, 0.0, 0.0])  # 默认值
            
            # 将法线转换到世界坐标系
            world_normal = rotation_matrix @ local_normal
            world_normal = world_normal / np.linalg.norm(world_normal) if np.linalg.norm(world_normal) > 0 else normal
            
            return RaycastResult(geometry, t, world_hit, world_normal)
        
        return RaycastResult()  # 未命中环 