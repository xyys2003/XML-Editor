"""
光线投射器

用于在3D场景中进行物体选择的射线投射器实现。
"""

import numpy as np
from typing import List, Optional, Tuple, Dict
from .geometry import BaseGeometry, GeometryGroup

class RaycastResult:
    """
    射线投射结果类，存储命中的几何体和命中点信息
    """
    def __init__(self, geometry=None, distance=float('inf'), hit_point=None, normal=None):
        self.geometry = geometry  # 命中的几何体
        self.distance = distance  # 射线起点到命中点的距离
        self.hit_point = hit_point or np.zeros(3)  # 世界坐标系中的命中点
        self.normal = normal or np.zeros(3)  # 命中点的表面法线
    
    def is_hit(self):
        """判断是否命中了物体"""
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
            if hasattr(geo, 'type') and geo.type != 'group':  # 只测试实际几何体，不测试组
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
        # 基于几何体类型进行不同的相交测试
        if geometry.type == 'box':
            return self._intersect_box(geometry, ray_origin, ray_direction)
        elif geometry.type == 'sphere':
            return self._intersect_sphere(geometry, ray_origin, ray_direction)
        elif geometry.type in ['cylinder', 'capsule']:
            return self._intersect_cylinder(geometry, ray_origin, ray_direction)
        elif geometry.type == 'plane':
            return self._intersect_plane(geometry, ray_origin, ray_direction)
        else:
            # 默认使用AABB（轴对齐包围盒）检测
            return self._intersect_aabb(geometry, ray_origin, ray_direction)
    
    def _intersect_box(self, geometry, ray_origin, ray_direction) -> RaycastResult:
        """盒子碰撞检测"""
        # 将射线从世界空间变换到物体局部空间
        inv_transform = np.linalg.inv(geometry.transform_matrix)
        local_ray_origin = inv_transform @ np.append(ray_origin, 1.0)
        local_ray_origin = local_ray_origin[:3]
        
        # 方向向量变换（不考虑平移）
        rotation_matrix = inv_transform[:3, :3]
        local_ray_direction = rotation_matrix @ ray_direction
        local_ray_direction = local_ray_direction / np.linalg.norm(local_ray_direction)
        
        # 在局部空间中与单位盒[-1,1]^3相交
        min_bounds = np.array([-1, -1, -1])
        max_bounds = np.array([1, 1, 1])
        
        t_min = (min_bounds - local_ray_origin) / local_ray_direction
        t_max = (max_bounds - local_ray_origin) / local_ray_direction
        
        # 确保t_min和t_max中较小的值在t_min中
        t1 = np.minimum(t_min, t_max)
        t2 = np.maximum(t_min, t_max)
        
        t_near = np.max(t1)
        t_far = np.min(t2)
        
        if t_near > t_far or t_far < 0:
            return RaycastResult()  # 未命中
        
        # 相交点在t_near处
        if t_near < 0:
            t_near = t_far  # 射线起点在盒子内部
        
        # 计算世界空间中的命中点
        local_hit_point = local_ray_origin + t_near * local_ray_direction
        
        # 计算法线（基于哪个面被命中）
        local_normal = np.zeros(3)
        for i in range(3):
            if abs(local_hit_point[i] - min_bounds[i]) < 1e-5:
                local_normal[i] = -1
                break
            elif abs(local_hit_point[i] - max_bounds[i]) < 1e-5:
                local_normal[i] = 1
                break
        
        # 将命中点和法线转换回世界空间
        world_hit_point = geometry.transform_matrix @ np.append(local_hit_point, 1.0)
        world_hit_point = world_hit_point[:3]
        
        # 法线矩阵（逆转置）
        normal_matrix = np.linalg.inv(rotation_matrix).T
        world_normal = normal_matrix @ local_normal
        world_normal = world_normal / np.linalg.norm(world_normal)
        
        # 计算射线起点到命中点的距离
        distance = np.linalg.norm(world_hit_point - ray_origin)
        
        return RaycastResult(geometry, distance, world_hit_point, world_normal)
    
    def _intersect_sphere(self, geometry, ray_origin, ray_direction) -> RaycastResult:
        """球体碰撞检测"""
        # 球心在世界坐标系中的位置
        sphere_center = geometry.get_world_position()
        
        # 球半径（假设所有维度使用相同的缩放值）
        radius = geometry.size[0]  # 使用第一个尺寸分量作为半径
        
        # 计算射线起点到球心的向量
        oc = ray_origin - sphere_center
        
        # 计算二次方程系数
        a = np.dot(ray_direction, ray_direction)
        b = 2.0 * np.dot(oc, ray_direction)
        c = np.dot(oc, oc) - radius * radius
        
        # 计算判别式
        discriminant = b * b - 4 * a * c
        
        if discriminant < 0:
            return RaycastResult()  # 未命中
        
        # 计算较近的交点
        t = (-b - np.sqrt(discriminant)) / (2.0 * a)
        
        if t < 0:
            # 射线起点在球内，尝试另一个交点
            t = (-b + np.sqrt(discriminant)) / (2.0 * a)
            if t < 0:
                return RaycastResult()  # 两个交点都在射线反方向
        
        # 计算交点位置
        hit_point = ray_origin + t * ray_direction
        
        # 计算法线
        normal = hit_point - sphere_center
        normal = normal / np.linalg.norm(normal)
        
        # 计算距离
        distance = t
        
        return RaycastResult(geometry, distance, hit_point, normal)
    
    def _intersect_cylinder(self, geometry, ray_origin, ray_direction) -> RaycastResult:
        """使用简化的AABB碰撞检测替代圆柱体检测"""
        return self._intersect_aabb(geometry, ray_origin, ray_direction)
    
    def _intersect_plane(self, geometry, ray_origin, ray_direction) -> RaycastResult:
        """平面碰撞检测"""
        # 获取平面法线（假设平面的局部空间中法线朝向y轴）
        local_normal = np.array([0, 1, 0])
        
        # 将法线变换到世界空间
        rotation_matrix = geometry.transform_matrix[:3, :3]
        normal = rotation_matrix @ local_normal
        normal = normal / np.linalg.norm(normal)
        
        # 平面上的一点（变换后的原点）
        plane_point = geometry.get_world_position()
        
        # 计算射线与平面的交点
        denom = np.dot(normal, ray_direction)
        
        if abs(denom) < 1e-6:
            return RaycastResult()  # 射线平行于平面
        
        t = np.dot(plane_point - ray_origin, normal) / denom
        
        if t < 0:
            return RaycastResult()  # 平面在射线反方向
        
        # 计算交点
        hit_point = ray_origin + t * ray_direction
        
        # 检查交点是否在平面范围内（简化为AABB检查）
        local_hit = np.linalg.inv(geometry.transform_matrix) @ np.append(hit_point, 1.0)
        if (abs(local_hit[0]) > geometry.size[0] or 
            abs(local_hit[2]) > geometry.size[2]):
            return RaycastResult()  # 交点不在平面范围内
        
        # 计算距离
        distance = t
        
        return RaycastResult(geometry, distance, hit_point, normal)
    
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