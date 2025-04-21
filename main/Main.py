import sys
import numpy as np
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QObject
from PyQt5.QtCore import QSignalBlocker 
from PyQt5.QtGui import QKeySequence
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import QModelIndex, QItemSelectionModel
from Raycaster import GeometryRaycaster, RaycastResult
from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *
import xml.etree.ElementTree as ET
from PyQt5.QtWidgets import QColorDialog  # 对话框类在QtWidgets模块
from PyQt5.QtGui import QColor            # 颜色类在QtGui模块        
from PyQt5.QtGui import QPixmap  # 新增这行
from PyQt5.QtGui import QDrag
from PyQt5.QtCore import Qt, QMimeData  # QMimeData 在 QtCore 中
from PyQt5.QtGui import QIcon

from copy import deepcopy
from contextlib import contextmanager

from Geomentry import TransformMode, Material, GeometryType as OriginalGeometryType, Geometry, OperationMode
from Geomentry import GeometryGroup

from OpenGLWidget import OpenGLWidget
from Controlpanel import ControlPanel
from PropertyPanel import PropertyPanel
from HierarchyTree import HierarchyTree
from Xmlparser import XMLParser


# 创建一个扩展的GeometryType类
class GeometryType(OriginalGeometryType):
    if not hasattr(OriginalGeometryType, 'ELLIPSOID'):
        ELLIPSOID = 'ellipsoid'

if not hasattr(GeometryType, 'ELLIPSOID'):
    setattr(GeometryType, 'ELLIPSOID', 'ellipsoid')

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



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenGL 3D编辑器")
        
        # 创建OpenGL窗口
        self.gl_widget = OpenGLWidget()
        self.setCentralWidget(self.gl_widget)
        
        # 创建控制面板
        self.control_panel = ControlPanel(self.gl_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.control_panel)
        
        # 创建属性面板
        self.property_panel = PropertyPanel(self.gl_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.property_panel)
        
        # 创建层级树
        self.hierarchy_tree = HierarchyTree(self.gl_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.hierarchy_tree)
        
        # 连接信号
        self.gl_widget.selection_changed.connect(self.property_panel.on_selection_changed)
        self.gl_widget.selection_changed.connect(self.hierarchy_tree.update_selection)
        self.gl_widget.geometriesChanged.connect(self.hierarchy_tree.refresh)
        
        # 创建菜单栏
        self.create_menus()
        
        # 添加全局快捷键
        self.setup_shortcuts()
        
        # 设置窗口大小
        self.resize(1200, 800)
    
    def setup_shortcuts(self):
        """设置全局快捷键"""
        # 复制快捷键
        copy_shortcut = QShortcut(QKeySequence.Copy, self)
        copy_shortcut.activated.connect(self._handle_copy)
        
        # 粘贴快捷键
        paste_shortcut = QShortcut(QKeySequence.Paste, self)
        paste_shortcut.activated.connect(self._handle_paste)
    
    def _handle_copy(self):
        """处理复制快捷键"""
        if len(self.gl_widget.selected_geos) > 1:
            self.hierarchy_tree._execute_multi_selection_action(
                self.hierarchy_tree._copy_object
            )
        elif self.gl_widget.selected_geo:
            self.hierarchy_tree._copy_object(self.gl_widget.selected_geo)
    
    def _handle_paste(self):
        """处理粘贴快捷键"""
        if self.hierarchy_tree._clipboard is not None:
            # 不论是单选还是多选，都使用同一个粘贴逻辑
            selected_obj = self.gl_widget.selected_geo
            self.hierarchy_tree._paste_object(selected_obj)
    
    def create_menus(self):
        # 文件菜单
        file_menu = self.menuBar().addMenu("文件")
        
        open_action = QAction("打开", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.export_to_mujoco)
        file_menu.addAction(save_action)

        # 添加导出到Mujoco XML选项

    def export_to_mujoco(self):
        """导出场景为Mujoco XML格式"""
        filename, _ = QFileDialog.getSaveFileName(self, "导出为Mujoco XML", "", "XML 文件 (*.xml)")
        if filename:
            try:
                success = XMLParser.export_mujoco_xml(filename, self.gl_widget.geometries)
                if success:
                    QMessageBox.information(self, "导出成功", f"场景已成功导出为Mujoco XML: {filename}")
                else:
                    QMessageBox.warning(self, "导出失败", 
                                       "导出Mujoco XML时发生错误。\n请确保已安装lxml库：pip install lxml")
            except Exception as e:
                QMessageBox.critical(self, "导出错误", f"导出过程中发生错误: {str(e)}")

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "打开场景文件", "", "XML Files (*.xml)")
        if filename:
            self.gl_widget.geometries = XMLParser.load(filename)
            self.hierarchy_tree.refresh()
            self.gl_widget.update()
    
    def save_file(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存场景文件", "", "XML Files (*.xml)")
        if filename:
            XMLParser.save(filename, self.gl_widget.geometries)






if __name__ == '__main__':


    import sys
    print(1)
    QApplication.setAttribute(Qt.AA_UseDesktopOpenGL)  # 兼容性设置
    print(2)
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)  # 共享上下文
    app = QApplication(sys.argv)
    print(3)
    try:
        print(4)

        window = MainWindow()
        print(5)
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(4.5)

        print(f"程序崩溃: {e}")
        QMessageBox.critical(None, "错误", f"程序崩溃: {str(e)}")