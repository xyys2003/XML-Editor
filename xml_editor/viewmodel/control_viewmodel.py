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

    @property
    def operation_mode(self):
        """获取当前操作模式"""
        return self._scene_viewmodel.operation_mode
    
    @operation_mode.setter
    def operation_mode(self, value):
        """设置操作模式"""
        self._scene_viewmodel.operation_mode = value
        self.operationModeChanged.emit(value)
