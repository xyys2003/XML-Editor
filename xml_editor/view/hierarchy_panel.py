# 假设有一个包含层级树的面板类
class HierarchyPanel(QWidget):
    def __init__(self, hierarchy_viewmodel, parent=None):
        super().__init__(parent)
        self._hierarchy_viewmodel = hierarchy_viewmodel
        
        # 创建布局
        layout = QVBoxLayout(self)
        
        # 创建层级树
        self.tree = HierarchyTree(hierarchy_viewmodel)
        
        # 创建刷新按钮
        refresh_button = self.tree.create_refresh_button()
        
        # 添加到布局
        layout.addWidget(refresh_button)
        layout.addWidget(self.tree)
        
        self.setLayout(layout) 