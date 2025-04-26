"""
MuJoCo场景编辑器主入口

初始化应用程序并连接各个组件。
"""

import sys
import os
from PyQt5.QtWidgets import QApplication, QMainWindow, QDockWidget, QMessageBox, QFileDialog, QAction
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence

# 导入视图模型
from .viewmodel.scene_viewmodel import SceneViewModel
from .viewmodel.property_viewmodel import PropertyViewModel
from .viewmodel.hierarchy_viewmodel import HierarchyViewModel
from .viewmodel.control_viewmodel import ControlViewModel

# 导入视图组件
from .view.opengl_view import OpenGLView
from .view.property_panel import PropertyPanel
from .view.hierarchy_tree import HierarchyTree
from .view.control_panel import ControlPanel

class MainWindow(QMainWindow):
    """
    主窗口类
    
    管理应用程序的所有UI组件和视图模型
    """
    def __init__(self):
        super().__init__()
        
        # 设置窗口标题和大小
        self.setWindowTitle("MuJoCo场景编辑器")
        self.resize(1200, 800)
        
        # 创建视图模型
        self.scene_viewmodel = SceneViewModel()
        self.property_viewmodel = PropertyViewModel(self.scene_viewmodel)
        self.hierarchy_viewmodel = HierarchyViewModel(self.scene_viewmodel)
        self.control_viewmodel = ControlViewModel(self.scene_viewmodel)
        
        # 创建视图组件
        self.opengl_view = OpenGLView(self.scene_viewmodel)
        self.property_panel = PropertyPanel(self.property_viewmodel)
        self.hierarchy_tree = HierarchyTree(self.hierarchy_viewmodel)
        self.control_panel = ControlPanel(self.control_viewmodel)
        
        # 设置中央窗口部件
        self.setCentralWidget(self.opengl_view)
        
        # 添加停靠窗口
        self._setup_dock_widgets()
        
        # 创建菜单栏
        self._create_menus()
        
        # 添加状态栏
        self.statusBar().showMessage("就绪")
        
        # 记录当前打开的文件
        self.current_file = None
    
    def _setup_dock_widgets(self):
        """设置停靠窗口"""
        # 层级树面板（左侧）
        hierarchy_dock = QDockWidget("层级结构", self)
        hierarchy_dock.setWidget(self.hierarchy_tree)
        hierarchy_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, hierarchy_dock)
        
        # 控制面板（左侧）
        control_dock = QDockWidget("控制面板", self)
        control_dock.setWidget(self.control_panel)
        control_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, control_dock)
        
        # 属性面板（右侧）
        property_dock = QDockWidget("属性", self)
        property_dock.setWidget(self.property_panel)
        property_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, property_dock)
    
    def _create_menus(self):
        """创建菜单"""
        # 文件菜单
        file_menu = self.menuBar().addMenu("文件(&F)")
        
        # 新建场景
        new_action = QAction("新建(&N)", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._new_scene)
        file_menu.addAction(new_action)
        
        # 打开
        open_action = QAction("打开(&O)...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)
        
        # 分隔线
        file_menu.addSeparator()
        
        # 保存
        save_action = QAction("保存(&S)", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_file)
        file_menu.addAction(save_action)
        
        # 另存为
        save_as_action = QAction("另存为(&A)...", self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self._save_file_as)
        file_menu.addAction(save_as_action)
        
        # 分隔线
        file_menu.addSeparator()
        
        # 退出
        exit_action = QAction("退出(&Q)", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 编辑菜单
        edit_menu = self.menuBar().addMenu("编辑(&E)")
        
        # 撤销/重做（这些功能需要在后续实现）
        undo_action = QAction("撤销(&U)", self)
        undo_action.setShortcut(QKeySequence.Undo)
        # undo_action.triggered.connect(self._undo)
        edit_menu.addAction(undo_action)
        undo_action.setEnabled(False)  # 暂时禁用
        
        redo_action = QAction("重做(&R)", self)
        redo_action.setShortcut(QKeySequence.Redo)
        # redo_action.triggered.connect(self._redo)
        edit_menu.addAction(redo_action)
        redo_action.setEnabled(False)  # 暂时禁用
        
        # 分隔线
        edit_menu.addSeparator()
        
        # 复制
        copy_action = QAction("复制(&C)", self)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(self._copy)
        edit_menu.addAction(copy_action)
        
        # 粘贴
        paste_action = QAction("粘贴(&P)", self)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.triggered.connect(self._paste)
        edit_menu.addAction(paste_action)
        
        # 删除
        delete_action = QAction("删除(&D)", self)
        delete_action.setShortcut(QKeySequence.Delete)
        delete_action.triggered.connect(self._delete)
        edit_menu.addAction(delete_action)
        
        # 视图菜单
        view_menu = self.menuBar().addMenu("视图(&V)")
        
        # 重置视图
        reset_view_action = QAction("重置视图", self)
        reset_view_action.triggered.connect(self._reset_all_views)
        view_menu.addAction(reset_view_action)
        
        # 帮助菜单
        help_menu = self.menuBar().addMenu("帮助(&H)")
        
        # 关于
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _new_scene(self):
        """创建新场景"""
        # 提示保存当前场景
        if len(self.scene_viewmodel.geometries) > 0:
            reply = QMessageBox.question(
                self, "创建新场景", 
                "创建新场景将丢失当前场景的所有更改。是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                return
        
        # 清空当前场景
        self.scene_viewmodel.geometries = []
        # 重置当前文件
        self.current_file = None
        # 更新窗口标题
        self.setWindowTitle("MuJoCo场景编辑器")
        self.statusBar().showMessage("已创建新场景")
    
    def _open_file(self):
        """打开文件"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "打开场景", "", "XML文件 (*.xml);;所有文件 (*)"
        )
        
        if filename:
            if self.scene_viewmodel.load_scene(filename):
                # 记录当前打开的文件
                self.current_file = filename
                # 更新窗口标题以显示当前文件名
                self.setWindowTitle(f"MuJoCo场景编辑器 - {os.path.basename(filename)}")
                self.statusBar().showMessage(f"已加载场景: {os.path.basename(filename)}")
            else:
                QMessageBox.warning(self, "加载错误", "无法加载场景文件。")
    
    def _save_file(self):
        """保存文件"""
        # 如果已有当前文件，直接保存到该文件
        if self.current_file:
            if self.scene_viewmodel.save_scene(self.current_file):
                self.statusBar().showMessage(f"已保存场景: {os.path.basename(self.current_file)}")
            else:
                QMessageBox.warning(self, "保存错误", "无法保存场景文件。")
        else:
            # 如果没有当前文件，则调用另存为
            self._save_file_as()
    
    def _save_file_as(self):
        """另存为"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存场景", "", "XML文件 (*.xml);;所有文件 (*)"
        )
        
        if filename:
            if not filename.lower().endswith(('.xml')):
                filename += '.xml'
                
            if self.scene_viewmodel.save_scene(filename):
                # 更新当前文件
                self.current_file = filename
                # 更新窗口标题
                self.setWindowTitle(f"MuJoCo场景编辑器 - {os.path.basename(filename)}")
                self.statusBar().showMessage(f"已保存场景: {os.path.basename(filename)}")
            else:
                QMessageBox.warning(self, "保存错误", "无法保存场景文件。")
    
    def _copy(self):
        """复制当前选中的几何体"""
        selected = self.scene_viewmodel.selected_geometry
        if selected:
            if self.hierarchy_viewmodel.copy_geometry(selected):
                self.statusBar().showMessage(f"已复制: {selected.name}")
    
    def _paste(self):
        """粘贴几何体"""
        result = self.hierarchy_viewmodel.paste_geometry()
        if result:
            self.statusBar().showMessage(f"已粘贴: {result.name}")
    
    def _delete(self):
        """删除当前选中的几何体"""
        selected = self.scene_viewmodel.selected_geometry
        if selected:
            name = selected.name
            self.hierarchy_viewmodel.remove_geometry(selected)
            self.statusBar().showMessage(f"已删除: {name}")
    
    def _show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self, 
            "关于MuJoCo场景编辑器", 
            "MuJoCo场景编辑器 v0.1.0\n\n"
            "一个用于创建和编辑MuJoCo场景的图形界面工具。"
        )
    
    def _reset_all_views(self):
        """重置所有视图"""
        # 重置3D视图
        self.opengl_view.reset_camera()
        
        # 重置并确保属性面板可见
        self.property_viewmodel.reset_properties()
        
        # 检查属性面板是否存在并可见，如果不可见则重新创建
        for dock in self.findChildren(QDockWidget):
            if dock.windowTitle() == "属性":
                if not dock.isVisible():
                    # 如果属性面板被关闭，重新显示它
                    dock.setVisible(True)
                    dock.raise_()
                break
        else:
            # 如果没有找到属性面板，重新创建
            self._recreate_property_panel()
        
        # 通知状态栏
        self.statusBar().showMessage("已重置所有视图")
    
    def _recreate_property_panel(self):
        """重新创建属性面板"""
        # 创建新的属性面板
        property_dock = QDockWidget("属性", self)
        property_dock.setWidget(self.property_panel)
        property_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, property_dock)
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 提示保存
        if len(self.scene_viewmodel.geometries) > 0:
            reply = QMessageBox.question(
                self, "退出程序", 
                "是否保存当前场景？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )
            
            if reply == QMessageBox.Save:
                self._save_file()
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    """应用程序入口点"""
    # 设置应用程序
    app = QApplication(sys.argv)
    app.setApplicationName("MuJoCo场景编辑器")
    
    # 启用OpenGL
    QApplication.setAttribute(Qt.AA_UseDesktopOpenGL)
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    
    # 创建主窗口
    window = MainWindow()
    window.show()
    
    # 运行应用程序
    sys.exit(app.exec_())


if __name__ == "__main__":
    main() 