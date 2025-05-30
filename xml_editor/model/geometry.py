"""
几何体模型类

定义了场景中的几何体数据结构及其操作。
"""

import numpy as np
from enum import Enum, auto
from scipy.spatial.transform import Rotation as R

class OperationMode(Enum):
    """操作模式枚举"""
    OBSERVE = auto()
    TRANSLATE = auto()
    ROTATE = auto()
    SCALE = auto()

class GeometryType(Enum):
    """几何体类型枚举"""
    BOX = "box"
    SPHERE = "sphere"
    CYLINDER = "cylinder"
    CAPSULE = "capsule"
    PLANE = "plane"
    ELLIPSOID = "ellipsoid"
    TRIANGLE = "triangle"


class Material:
    """
    材质类，定义几何体的外观属性
    """
    def __init__(self):
        self._base_color = np.array([1.0, 1.0, 1.0, 1.0])  # 默认白色
        self.specular = np.array([0.5, 0.5, 0.5, 1.0])
        self.shininess = 32.0
    
    @property
    def color(self):
        """主颜色访问接口（RGBA格式）"""
        return self._base_color
    
    @color.setter
    def color(self, value):
        """设置颜色，接受RGB或RGBA值"""
        if len(value) not in (3, 4):
            raise ValueError("颜色值应为RGB或RGBA格式")
        
        if len(value) == 3:
            self._base_color = np.array([*value, 1.0], dtype=np.float32)
        else:
            self._base_color = np.array(value, dtype=np.float32)


class BaseGeometry:
    """
    几何体基类，定义了所有几何体的通用属性和方法
    """
    def __init__(self, geo_type, name="Object", position=(0, 0, 0), 
                 size=(1, 1, 1), rotation=(0, 0, 0), parent=None):
        self.type = geo_type
        self.name = name
        self._visible = True
        self._position = np.array(position, dtype=np.float32)
        self._size = np.array(size, dtype=np.float32)
        self._rotation = np.array(rotation, dtype=np.float32)
        self.parent = parent
        self.children = []
        self.material = Material()
        self.aabb_min = np.zeros(3, dtype=np.float32)
        self.aabb_max = np.zeros(3, dtype=np.float32)
        self.transform_matrix = np.eye(4)
       
        # 设置默认颜色
        type_colors = {
            GeometryType.BOX.value: (0.8, 0.5, 0.2, 1.0),    # 橙色
            GeometryType.SPHERE.value: (0.2, 0.8, 0.5, 1.0),  # 绿色
            GeometryType.CYLINDER.value: (0.5, 0.2, 0.8, 1.0),  # 紫色
            GeometryType.CAPSULE.value: (0.2, 0.5, 0.8, 1.0),  # 蓝色
            GeometryType.PLANE.value: (0.7, 0.7, 0.7, 1.0),   # 灰色
            GeometryType.ELLIPSOID.value: (0.8, 0.2, 0.2, 1.0),  # 红色
            GeometryType.TRIANGLE.value: (0.2, 0.8, 0.8, 1.0),  # 青色
        }
        self.material.color = type_colors.get(geo_type, (1.0, 1.0, 1.0, 1.0))
        
        self._update_transform()
        self._update_aabb()
    
    @property
    def visible(self):
        """获取可见性"""
        return self._visible
    
    @visible.setter
    def visible(self, value):
        """设置可见性"""
        self._visible = value

    @property
    def position(self):
        """获取位置"""
        return self._position
    
    @position.setter
    def position(self, value):
        """设置位置"""
        self._position = np.array(value)
        self._update_transform()
        self._update_aabb()
    
    @property
    def size(self):
        """获取尺寸"""
        return self._size
    
    @size.setter
    def size(self, value):
        """设置尺寸"""
        self._size = np.array(value)
        self._update_transform()
        self._update_aabb()
    
    @property
    def rotation(self):
        """获取旋转角度"""
        return self._rotation
    
    @rotation.setter
    def rotation(self, value):
        """设置旋转角度"""
        self._rotation = np.array(value, dtype=np.float32)
        self._update_transform()
        self._update_aabb()
    
    @property
    def aabb_bounds(self):
        """返回包围盒边界"""
        return [self.aabb_min, self.aabb_max]
    
    def add_child(self, child):
        """添加子对象"""
        self.children.append(child)
        child.parent = self
        child.update_transform_matrix()
    
    def remove_child(self, child):
        """移除子对象"""
        if child in self.children:
            self.children.remove(child)
            child.parent = None
    
    def _update_aabb(self):
        """更新几何体的轴对齐包围盒"""
        # 将 size 转换为与 position 相同的形状
        size_array = np.array(self.size)
        if size_array.shape != self.position.shape:
            # 如果维度不匹配，进行填充或截断
            if len(size_array) < len(self.position):
                # 如果 size 维度不足，填充到与 position 相同的维度
                padded_size = np.zeros_like(self.position)
                padded_size[:len(size_array)] = size_array
                size_array = padded_size
            else:
                # 如果 size 维度过多，截断到与 position 相同的维度
                size_array = size_array[:len(self.position)]
        
        # 计算 AABB
        self.aabb_min = self.position - size_array
        self.aabb_max = self.position + size_array
    
    def _update_transform(self):
        """更新变换矩阵"""
        # 使用scipy的Rotation创建旋转矩阵，注意使用角度制
        rot_3x3 = R.from_euler('XYZ', self.rotation, degrees=True).as_matrix()
        translation_matrix = np.eye(4)
        translation_matrix[:3, 3] = self.position
        translation_matrix[:3, :3] = rot_3x3
        
        self.transform_matrix = translation_matrix
    
    def update_transform_matrix(self):
        """更新变换矩阵，考虑位置、旋转和父节点"""
        # 先更新自身的局部变换矩阵
        self._update_transform()
        
        # 如果有父节点，需要考虑父节点的变换
        if self.parent is not None and hasattr(self.parent, 'transform_matrix'):
            self.transform_matrix = self.parent.transform_matrix @ self.transform_matrix
        
        # 递归更新所有子节点的变换矩阵
        for child in self.children:
            if hasattr(child, 'update_transform_matrix'):
                child.update_transform_matrix()
    
    def get_all_geometries(self):
        """获取所有子几何体（包括自己）"""
        result = [self]
        for child in self.children:
            result.extend(child.get_all_geometries())
        return result
    
    def get_world_transform(self):
        """获取世界变换矩阵"""
        return self.transform_matrix
    
    def get_world_position(self):
        """获取世界坐标系中的位置"""
        return self.transform_matrix[:3, 3]

    def get_specific_properties(self):
        """
        获取几何体特有的属性
        
        返回:
            dict: 包含几何体特有属性的字典
        """
        # 基础实现返回空字典，由具体子类重写
        return {}


class Geometry(BaseGeometry):
    """
    具体几何体类，可直接使用
    """
    def __init__(self, geo_type, name="Object", position=(0, 0, 0), 
                 size=(1, 1, 1), rotation=(0, 0, 0), parent=None):
        super().__init__(geo_type, name, position, size, rotation, parent)


class GeometryGroup(BaseGeometry):
    """
    几何体组类，用于创建层级结构
    """
    def __init__(self, name="Group", position=(0, 0, 0), rotation=(0, 0, 0), parent=None):
        super().__init__(None, name, position, (1, 1, 1), rotation, parent)
        self.type = "group"  # 特殊类型
    
    @property
    def size(self):
        """获取尺寸"""
        return self._size
    
    @size.setter
    def size(self, value):
        """设置尺寸（仅用于显示，不影响子对象）"""
        self._size = np.array(value)
        self._update_transform()
        self._update_aabb()
        # 注意：不更新子对象的大小
    
    def _update_children_transforms(self):
        """更新所有子对象的变换矩阵"""
        for child in self.children:
            child.update_transform_matrix()
            if hasattr(child, '_update_children_transforms'):
                child._update_children_transforms()


class TriangleGeometry(Geometry):
    """
    三角形几何体类
    """
    def __init__(self, name="Triangle", position=(0, 0, 0), 
                 size=(1, 1, 1), rotation=(0, 0, 0), parent=None):
        super().__init__(GeometryType.TRIANGLE.value, name, position, size, rotation, parent) 

# 打印这里的实际值
print("有效的几何体类型：")
for geo_type in GeometryType:
    print(f"  {geo_type.name}: {geo_type.value}") 