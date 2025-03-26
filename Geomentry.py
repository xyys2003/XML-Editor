import sys
import numpy as np
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QObject
from PyQt5.QtCore import QSignalBlocker 
from PyQt5.QtGui import QKeySequence
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import QModelIndex, QItemSelectionModel
from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *
import xml.etree.ElementTree as ET
from PyQt5.QtWidgets import QColorDialog  # 对话框类在QtWidgets模块
from PyQt5.QtGui import QColor            # 颜色类在QtGui模块        
from PyQt5.QtGui import QPixmap  # 新增这行

from copy import deepcopy
from contextlib import contextmanager

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
    
        # ...类似生成Ry和Rz...
    rotation_3x3 = Rz @ Ry @ Rx
    
    # 扩展为4x4齐次矩阵
    matrix_4x4 = np.eye(4)
    matrix_4x4[:3, :3] = rotation_3x3
    return matrix_4x4

# ========== 常量定义 ==========
class TransformMode:
    TRANSLATE, ROTATE, SCALE = range(3)

class Material:
    def __init__(self):
        # 新增颜色属性体系（参考网页2的Unity动态设置模式）
        self._base_color = np.array([1.0, 1.0, 1.0, 1.0])  # 默认白色[4](@ref)
        self.specular = np.array([0.5, 0.5, 0.5, 1.0])
        self.shininess = 32.0
    
    @property
    def color(self):
        """主颜色访问接口（RGBA格式）"""
        return self._base_color
    
    @color.setter
    def color(self, value):
        """带类型校验的颜色设置（参考网页3的API规范）"""
        if len(value) not in (3,4):
            raise ValueError("颜色值应为RGB或RGBA格式")
        self._base_color = np.array(value, dtype=np.float32)

class OperationMode:
    MODE_OBSERVE, MODE_TRANSLATE, MODE_ROTATE, MODE_SCALE  = range(4)


class GeometryType:
    BOX, SPHERE, CYLINDER, CAPSULE, PLANE, ELLIPSOID = 'box sphere cylinder capsule plane ellipsoid'.split()

class Geometry(QObject):
    changed = pyqtSignal()
    
    def __init__(self, geo_type, name="Object", position=(0,0,0), 
                 size=(1,1,1), rotation=(0,0,0), parent=None):
        super().__init__()
        self.type = geo_type
        self.name = name
        self._position = np.array(position, dtype=np.float32)
        self._size = np.array(size, dtype=np.float32)
        self._rotation = np.array(rotation, dtype=np.float32)
        self.parent = parent
        self.children = []
        self.selected = False
        self.material = Material()
        type_colors = {
            GeometryType.BOX: (0.8, 0.5, 0.2, 1.0),    # 橙色
            GeometryType.SPHERE: (0.2, 0.8, 0.5, 1.0)   # 绿色
        }
        self.material.color = type_colors.get(geo_type, (1.0,1.0,1.0,1.0))  # 默认白色[4](@ref)
    
        self.aabb_min = np.zeros(3, dtype=np.float32)
        self.aabb_max = np.zeros(3, dtype=np.float32)  
        self.transform_matrix = np.eye(4)  # 初始化为单位矩阵     
        self._update_aabb()  # 初始化时更新包围盒[2](@ref)
        self._update_transform()  # 初始化时计算矩阵
        
    @property
    def position(self):
        return self._position
    

    @position.setter 
    def position(self, value):
        self._position = np.array(value)
        self._update_transform()  # 更新矩阵
        self._update_aabb()  # 位置变化时更新包围盒[2](@ref)
        self.changed.emit()

    @property
    def aabb_bounds(self):
            """返回格式为[[min_x,min_y,min_z], [max_x,max_y,max_z]]的数组"""
            return self._aabb_bounds

    @property
    def size(self):
        return self._size
    
    @size.setter
    def size(self, value):
        self._size = np.array(value)
        self._update_transform()  # 更新矩阵
        self._update_aabb()  # 尺寸变化时更新包围盒[5](@ref)
        self.changed.emit()

    @property
    def rotation(self):
        return self._rotation
    
    @rotation.setter
    def rotation(self, value):
        self._rotation = np.array(value, dtype=np.float32)
        self._update_transform()  # 更新矩阵
        self._update_aabb()  # 新增：旋转后更新AABB[1](@ref)
        self.changed.emit()



    def _update_aabb(self):
        """根据 Mujoco 的半长半宽半高逻辑更新 AABB 包围盒"""
        if not hasattr(self, 'position') or not hasattr(self, 'size'):
            return
        
        # 不同几何体类型的包围盒计算略有不同
        if self.type == GeometryType.SPHERE:
            # 球体 - 使用半径作为 AABB 尺寸
            radius = self.size[0]
            self.aabb_min = self.position - radius
            self.aabb_max = self.position + radius
        elif self.type == GeometryType.ELLIPSOID:
            # 椭球体 - 使用三个方向的半径
            self.aabb_min = self.position - self.size
            self.aabb_max = self.position + self.size
        else:
            # 其他几何体 - 使用半尺寸计算
            # 考虑旋转的影响（简化处理）
            if np.any(self.rotation):
                # 有旋转时，使用最大半尺寸作为边界
                max_half_size = np.max(self.size)
                self.aabb_min = self.position - max_half_size
                self.aabb_max = self.position + max_half_size
            else:
                # 无旋转时，直接使用半尺寸
                self.aabb_min = self.position - self.size
                self.aabb_max = self.position + self.size
        
    def _update_transform(self):
        """根据位置/旋转/缩放更新变换矩阵（标准TRS顺序）"""
        # 先缩放，再旋转，最后平移
        scale_matrix = np.diag([self.size[0], self.size[1], self.size[2], 1.0])
        rotation_matrix = euler_angles_to_matrix(np.radians(self.rotation))
        translation_matrix = np.eye(4)
        translation_matrix[:3, 3] = self.position
        
        # 正确的乘法顺序: T * R * S
        self.transform_matrix = translation_matrix @ rotation_matrix @ scale_matrix

class GeometryGroup(QObject):
    """几何体分组/目录类，用于创建层级结构"""
    changed = pyqtSignal()
    
    def __init__(self, name="Group", position=(0,0,0), rotation=(0,0,0), parent=None):
        super().__init__()
        self.type = "group"  # 标识为分组
        self.name = name
        self._position = np.array(position, dtype=np.float32)
        self._rotation = np.array(rotation, dtype=np.float32)
        self._size = np.array([1,1,1], dtype=np.float32)  # 默认尺寸，用于界面显示
        self.parent = parent
        self.children = []  # 子对象列表(包含几何体和子组)
        self.selected = False
        self.transform_matrix = np.eye(4)  # 初始化为单位矩阵
        self._update_transform()  # 初始化时计算矩阵
        
    @property
    def position(self):
        return self._position
    
    @position.setter
    def position(self, value):
        self._position = np.array(value)
        self._update_transform()
        self._update_children_transforms()
        self.changed.emit()
    
    @property
    def rotation(self):
        return self._rotation
    
    @rotation.setter
    def rotation(self, value):
        self._rotation = np.array(value, dtype=np.float32)
        self._update_transform()
        self._update_children_transforms()
        self.changed.emit()
    
    @property
    def size(self):
        return self._size
    
    @size.setter
    def size(self, value):
        # 组的大小只是用于显示，不应该影响子对象
        self._size = np.array(value)
        self.changed.emit()
    
    def _update_transform(self):
        """更新当前组的变换矩阵"""
        # 创建旋转矩阵
        rotation_matrix = euler_angles_to_matrix(np.radians(self.rotation))
        
        # 创建平移矩阵
        translation_matrix = np.eye(4)
        translation_matrix[:3, 3] = self.position
        
        # 组合变换
        self.transform_matrix = translation_matrix @ rotation_matrix
        
        # 如果有父组，需要考虑父组的变换
        if self.parent:
            self.transform_matrix = self.parent.transform_matrix @ self.transform_matrix
    
    def _update_children_transforms(self):
        """更新所有子对象的变换，传播变换矩阵到子项"""
        # 确保我们有最新的自身变换矩阵
        if not hasattr(self, 'transform_matrix'):
            self._update_transform()
        
        # 对每个子对象处理
        for child in self.children:
            # 首先更新子对象自身的局部变换矩阵
            if hasattr(child, '_update_transform'):
                child._update_transform()
            
            # 如果子对象是组，递归更新其子项
            if isinstance(child, GeometryGroup):
                child._update_children_transforms()
    
    def add_child(self, child):
        """添加子对象(几何体或组)"""
        child.parent = self
        self.children.append(child)
        self.changed.emit()
        return child
    
    def remove_child(self, child):
        """移除子对象"""
        if child in self.children:
            self.children.remove(child)
            child.parent = None
            self.changed.emit()
    
    def get_all_geometries(self):
        """获取该组及其所有子组中的所有几何体"""
        geometries = []
        for child in self.children:
            if isinstance(child, Geometry):
                geometries.append(child)
            elif isinstance(child, GeometryGroup):
                geometries.extend(child.get_all_geometries())
        return geometries
    
    def get_world_transform(self):
        """计算组的世界变换矩阵，包括所有父组的变换"""
        if not hasattr(self, 'transform_matrix'):
            self._update_transform()
        return self.transform_matrix.copy()  # 返回副本以避免修改原始矩阵
    
    def get_world_position(self):
        """获取世界坐标系中的位置"""
        world_matrix = self.get_world_transform()
        return world_matrix[:3, 3]