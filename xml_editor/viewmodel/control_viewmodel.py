"""
控制面板视图模型

处理工具选择和操作模式等控制逻辑。
"""

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from ..model.geometry import OperationMode, GeometryType
from ..viewmodel.scene_viewmodel import SceneViewModel

class ControlViewModel(QObject):
    """
    控制面板视图模型类
    
    处理工具选择、操作模式和几何体创建等控制逻辑
    """
    # 信号
    operationModeChanged = pyqtSignal(object)  # 操作模式变化
    coordinateSystemChanged = pyqtSignal(bool)  # 坐标系变化，True表示局部坐标系，False表示全局坐标系
    
    def __init__(self, scene_viewmodel:SceneViewModel):
        """
        初始化控制面板视图模型
        
        参数:
            scene_viewmodel: 场景视图模型的引用
        """
        super().__init__()
        self._scene_viewmodel = scene_viewmodel
        
        # 连接场景视图模型的信号
        self._scene_viewmodel.operationModeChanged.connect(self.operationModeChanged)
        
        # 添加对坐标系变化的处理
        if hasattr(self._scene_viewmodel, 'coordinateSystemChanged'):
            self._scene_viewmodel.coordinateSystemChanged.connect(self.coordinateSystemChanged)

    @property
    def operation_mode(self):
        """获取当前操作模式"""
        return self._scene_viewmodel.operation_mode
    
    @operation_mode.setter
    def operation_mode(self, value):
        """设置操作模式"""
        self._scene_viewmodel.operation_mode = value
        self.operationModeChanged.emit(value)
    
    @property
    def use_local_coords(self):
        """获取当前坐标系模式，True表示局部坐标系，False表示全局坐标系"""
        return self._scene_viewmodel.use_local_coords if hasattr(self._scene_viewmodel, 'use_local_coords') else True
    
    @use_local_coords.setter
    def use_local_coords(self, value):
        """设置坐标系模式"""
        if hasattr(self._scene_viewmodel, 'use_local_coords'):
            self._scene_viewmodel.use_local_coords = value
            self.coordinateSystemChanged.emit(value)
