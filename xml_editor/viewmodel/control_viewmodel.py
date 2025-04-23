"""
控制面板视图模型

处理工具选择和操作模式等控制逻辑。
"""

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from ..model.geometry import TransformMode, OperationMode, GeometryType

class ControlViewModel(QObject):
    """
    控制面板视图模型类
    
    处理工具选择、操作模式和几何体创建等控制逻辑
    """
    # 信号
    transformModeChanged = pyqtSignal(object)  # 变换模式变化
    operationModeChanged = pyqtSignal(object)  # 操作模式变化
    
    def __init__(self, scene_viewmodel):
        """
        初始化控制面板视图模型
        
        参数:
            scene_viewmodel: 场景视图模型的引用
        """
        super().__init__()
        self._scene_viewmodel = scene_viewmodel
    
    @property
    def transform_mode(self):
        """获取当前变换模式"""
        return self._scene_viewmodel.transform_mode
    
    @transform_mode.setter
    def transform_mode(self, value):
        """设置变换模式"""
        self._scene_viewmodel.transform_mode = value
        self.transformModeChanged.emit(value)
    
    @property
    def operation_mode(self):
        """获取当前操作模式"""
        return self._scene_viewmodel.operation_mode
    
    @operation_mode.setter
    def operation_mode(self, value):
        """设置操作模式"""
        self._scene_viewmodel.operation_mode = value
        self.operationModeChanged.emit(value)
    
    def set_translate_mode(self):
        """设置为平移模式"""
        self.transform_mode = TransformMode.TRANSLATE
        self.operation_mode = OperationMode.TRANSLATE
    
    def set_rotate_mode(self):
        """设置为旋转模式"""
        self.transform_mode = TransformMode.ROTATE
        self.operation_mode = OperationMode.ROTATE
    
    def set_scale_mode(self):
        """设置为缩放模式"""
        self.transform_mode = TransformMode.SCALE
        self.operation_mode = OperationMode.SCALE
    
    def set_observe_mode(self):
        """设置为观察模式"""
        self.operation_mode = OperationMode.OBSERVE
    
    def create_box(self, parent=None):
        """
        创建盒子几何体
        
        参数:
            parent: 父对象（可选）
            
        返回:
            创建的几何体对象
        """
        return self._scene_viewmodel.create_geometry(
            geo_type=GeometryType.BOX.value,
            position=(0, 0, 0),
            size=(1, 1, 1),
            parent=parent
        )
    
    def create_sphere(self, parent=None):
        """
        创建球体几何体
        
        参数:
            parent: 父对象（可选）
            
        返回:
            创建的几何体对象
        """
        return self._scene_viewmodel.create_geometry(
            geo_type=GeometryType.SPHERE.value,
            position=(0, 0, 0),
            size=(0.5, 0.5, 0.5),  # 初始尺寸均为0.5，仅使用一个半径值
            parent=parent
        )
    
    def create_cylinder(self, parent=None):
        """
        创建圆柱体几何体
        
        参数:
            parent: 父对象（可选）
            
        返回:
            创建的几何体对象
        """
        return self._scene_viewmodel.create_geometry(
            geo_type=GeometryType.CYLINDER.value,
            position=(0, 0, 0),
            size=(0.5, 1.0, 0.5),  # 中间值为高度，x和z值为半径
            parent=parent
        )
    
    def create_capsule(self, parent=None):
        """
        创建胶囊体几何体
        
        参数:
            parent: 父对象（可选）
            
        返回:
            创建的几何体对象
        """
        return self._scene_viewmodel.create_geometry(
            geo_type=GeometryType.CAPSULE.value,
            position=(0, 0, 0),
            size=(0.5, 1.0, 0.5),  # 中间值为半高度，x和z值为半径
            parent=parent
        )
    
    def create_plane(self, parent=None):
        """
        创建平面几何体
        
        参数:
            parent: 父对象（可选）
            
        返回:
            创建的几何体对象
        """
        return self._scene_viewmodel.create_geometry(
            geo_type=GeometryType.PLANE.value,
            position=(0, 0, 0),
            size=(5.0, 0.1, 5.0),
            parent=parent
        )
    
    def create_group(self, parent=None):
        """
        创建几何体组
        
        参数:
            parent: 父对象（可选）
            
        返回:
            创建的几何体组对象
        """
        return self._scene_viewmodel.create_group(parent=parent) 