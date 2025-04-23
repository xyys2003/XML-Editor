"""
属性面板

包装属性视图(PropertyView)用于显示在停靠面板中。
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout

from .property_view import PropertyView

class PropertyPanel(QWidget):
    """
    属性面板类
    
    用于在停靠窗口中显示属性视图
    """
    
    def __init__(self, property_viewmodel, parent=None):
        """
        初始化属性面板
        
        参数:
            property_viewmodel: 属性视图模型的引用
            parent: 父窗口部件
        """
        super().__init__(parent)
        
        # 创建布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建属性视图并添加到布局中
        self.property_view = PropertyView(property_viewmodel)
        layout.addWidget(self.property_view)
        
        # 将属性视图的propertyChanged信号转发到视图模型
        self.property_view.propertyChanged.connect(property_viewmodel.set_property) 