"""
属性视图模型

作为属性视图和模型层之间的桥梁，处理属性相关的业务逻辑。
"""

from PyQt5.QtCore import QObject, pyqtSignal
from ..viewmodel.scene_viewmodel import SceneViewModel
class PropertyViewModel(QObject):
    """
    属性视图模型
    
    管理对象属性的业务逻辑，包括获取、设置属性值，并在属性更改时发出信号
    """
    # 信号：属性变化时触发，视图将更新显示
    propertiesChanged = pyqtSignal()
    
    # 添加新的信号
    propertyChanged = pyqtSignal(object, str, object)  # 属性变化信号（对象、属性名、新值）
    
    def __init__(self, scene_model:SceneViewModel):
        """
        初始化属性视图模型
        
        参数:
            scene_model: 场景模型的引用
        """
        super().__init__()
        self._scene_model = scene_model
        
        # 保存当前选中的对象
        self._selected_object = None
        
        # 连接场景模型的选择变化信号
        self._scene_model.selectionChanged.connect(self._on_selection_changed)
        
        # 连接对象属性变化信号
        self._scene_model.objectChanged.connect(self._on_object_changed)
    
    @property
    def selected_object(self):
        """获取当前选中的对象"""
        return self._selected_object
    
    def _on_selection_changed(self, selected_object):
        """
        处理场景中对象选择变化
        
        参数:
            selected_object: 新选中的对象
        """
        self._selected_object = selected_object
        self.propertiesChanged.emit()
    
    def _on_object_changed(self, obj):
        """
        处理对象属性变化
        
        参数:
            obj: 被修改的对象
        """
        if obj == self._selected_object:
            self.propertiesChanged.emit()
    
    def get_property(self, property_name):
        """
        获取对象的属性值
        
        参数:
            property_name: 属性名称
            
        返回:
            属性值或None（如果属性不存在或无选中对象）
        """
        if self._selected_object is None:
            return None
        
        # 基本属性
        if property_name == "name":
            return self._selected_object.name
        elif property_name == "type":
            if hasattr(self._selected_object.type, 'value'):
                return self._selected_object.type.value
            else:
                return self._selected_object.type  # 处理group类型，它的类型是字符串
        elif property_name == "visible":
            return getattr(self._selected_object, "visible", True)
        
        # 变换属性
        elif property_name == "position":
            return self._selected_object.position
        elif property_name == "position_x":
            return self._selected_object.position[0]
        elif property_name == "position_y":
            return self._selected_object.position[1]
        elif property_name == "position_z":
            return self._selected_object.position[2]
        
        elif property_name == "rotation":
            return self._selected_object.rotation
        elif property_name == "rotation_x":
            return self._selected_object.rotation[0]
        elif property_name == "rotation_y":
            return self._selected_object.rotation[1]
        elif property_name == "rotation_z":
            return self._selected_object.rotation[2]
        
        elif property_name == "scale":
            return self._selected_object.size
        elif property_name == "scale_x":
            return self._selected_object.size[0]
        elif property_name == "scale_y":
            return self._selected_object.size[1]
        elif property_name == "scale_z":
            return self._selected_object.size[2]
        
        # 材质属性
        elif property_name == "material_color":
            return self._selected_object.material.color
        
        return None
    
    def set_property(self, property_name, value):
        """
        设置对象的属性值
        
        参数:
            property_name: 属性名称
            value: 新的属性值
            
        返回:
            是否设置成功
        """
        if self._selected_object is None:
            return False
        
        # 类型属性不允许修改
        if property_name == "type":
            return False
            
        # 基本属性
        if property_name == "name":
            self._selected_object.name = value
        elif property_name == "visible":
            self._selected_object.visible = value
        
        # 变换属性
        elif property_name.startswith("position"):
            position = list(self._selected_object.position)
            
            if property_name == "position":
                position = value
            elif property_name == "position_x":
                position[0] = value
            elif property_name == "position_y":
                position[1] = value
            elif property_name == "position_z":
                position[2] = value
            
            self._selected_object.position = position
        
        elif property_name.startswith("rotation"):
            rotation = list(self._selected_object.rotation)
            
            if property_name == "rotation":
                rotation = value
            elif property_name == "rotation_x":
                rotation[0] = value
            elif property_name == "rotation_y":
                rotation[1] = value
            elif property_name == "rotation_z":
                rotation[2] = value
            
            self._selected_object.rotation = rotation
        
        elif property_name.startswith("scale"):
            size = list(self._selected_object.size)
            
            if property_name == "scale":
                size = value
            elif property_name == "scale_x":
                size[0] = value
            elif property_name == "scale_y":
                size[1] = value
            elif property_name == "scale_z":
                size[2] = value
            
            self._selected_object.size = size
        
        # 材质属性
        elif property_name == "material_color":
            self._selected_object.material.color = value
        
        else:
            return False
        
        # 发射属性变化信号
        self.propertyChanged.emit(self._selected_object, property_name, value)
        
        # 通知场景视图模型对象已更改
        self._scene_model.notify_object_changed(self._selected_object)
        return True
    
    def reset_properties(self):
        """
        重置属性面板
        
        清空当前选择并刷新属性面板
        """
        # 清除当前选择
        self._selected_object = None
        
        # 通知视图刷新
        self.propertiesChanged.emit() 