

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

from Geomentry import TransformMode, Material, GeometryType as OriginalGeometryType, Geometry, OperationMode
from Geomentry import GeometryGroup
from contextlib import contextmanager



class GeometryType(OriginalGeometryType):
    if not hasattr(OriginalGeometryType, 'ELLIPSOID'):
        ELLIPSOID = 'ellipsoid'

if not hasattr(GeometryType, 'ELLIPSOID'):
    setattr(GeometryType, 'ELLIPSOID', 'ellipsoid')


class PropertyPanel(QDockWidget):
    """显示和编辑选中几何体属性的面板"""
    def __init__(self, gl_widget):
        super().__init__("属性面板")
        self.gl_widget = gl_widget
        self.gl_widget.selection_changed.connect(self.on_selection_changed)
        
        # 添加当前几何体的引用
        self.current_geo = None
        self._in_update = False  # 添加更新标志
        
        # 创建主widget和布局
        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout()
        self.main_widget.setLayout(self.main_layout)
        
        # 创建表单布局
        self.form_layout = QFormLayout()
        self.main_layout.addLayout(self.form_layout)
        
        # 创建按钮布局
        self.button_layout = QHBoxLayout()
        
        # 创建确定和取消按钮
        self.apply_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        
        # 添加按钮到布局
        self.button_layout.addWidget(self.apply_button)
        self.button_layout.addWidget(self.cancel_button)
        
        # 将按钮布局添加到主布局
        self.main_layout.addLayout(self.button_layout)
        
        # 连接按钮信号
        self.apply_button.clicked.connect(self._on_apply)
        self.cancel_button.clicked.connect(self._on_cancel)
        
        # 存储临时数据的变量
        self.temp_data = {}
        
        self.setWidget(self.main_widget)
        
    def on_selection_changed(self, geo):
        """当选择变更时更新面板内容"""
        self.current_geo = geo  # 更新当前几何体引用
        self._in_update = True  # 设置更新标志
        
        try:
            # 清除旧的控件
            self.clear_layout(self.form_layout)
            
            if not geo:
                return
                
            # 保存当前物体的原始数据
            self.temp_data = {
                'name': geo.name,
                'position': geo.position.copy(),
                'rotation': geo.rotation.copy(),
                'size': geo.size.copy()
            }
            
            if hasattr(geo, 'material'):
                self.temp_data['color'] = geo.material.color.copy()
            
            # 创建名称输入框
            self.name_edit = QLineEdit(geo.name)
            self.form_layout.addRow("名称:", self.name_edit)
            
            # 创建位置、旋转、缩放的spinner
            self.pos_spinners = []
            self.rot_spinners = []
            self.scale_spinners = []
            
            # 位置控件
            pos_widget = QWidget()
            pos_layout = QHBoxLayout()
            pos_widget.setLayout(pos_layout)
            for i, val in enumerate(geo.position):
                spinner = self._create_spinbox()
                spinner.setValue(val)
                pos_layout.addWidget(spinner)
                self.pos_spinners.append(spinner)
            self.form_layout.addRow("位置:", pos_widget)
            
            # 旋转控件
            rot_widget = QWidget()
            rot_layout = QHBoxLayout()
            rot_widget.setLayout(rot_layout)
            for i, val in enumerate(geo.rotation):
                spinner = self._create_spinbox()
                spinner.setValue(val)
                rot_layout.addWidget(spinner)
                self.rot_spinners.append(spinner)
            self.form_layout.addRow("旋转:", rot_widget)
            
            # 缩放控件
            scale_widget = QWidget()
            scale_layout = QHBoxLayout()
            scale_widget.setLayout(scale_layout)
            for i, val in enumerate(geo.size):
                spinner = self._create_spinbox()
                spinner.setValue(val)
                scale_layout.addWidget(spinner)
                self.scale_spinners.append(spinner)
            self.form_layout.addRow("缩放:", scale_widget)
            
            # 如果是几何体，添加材质属性
            if hasattr(geo, 'material'):
                # 颜色选择按钮
                self.color_button = QPushButton()
                color = geo.material.color
                self.color_button.setStyleSheet(
                    f"background-color: rgb({int(color[0]*255)}, {int(color[1]*255)}, {int(color[2]*255)})")
                self.form_layout.addRow("颜色:", self.color_button)
            
            # 连接信号
            self._connect_signals()
            
        finally:
            self._in_update = False  # 确保标志被重置
    
    def _on_apply(self):
        """确定按钮点击处理"""
        if not self.current_geo:
            return
            
        # 应用所有更改
        with self._block_geo_signals():
            # 更新名称
            if hasattr(self, 'name_edit'):
                self.current_geo.name = self.name_edit.text()
            
            # 更新位置
            if hasattr(self, 'pos_spinners') and len(self.pos_spinners) == 3:
                self.current_geo.position = np.array([s.value() for s in self.pos_spinners])
            
            # 更新旋转
            if hasattr(self, 'rot_spinners') and len(self.rot_spinners) == 3:
                self.current_geo.rotation = np.array([s.value() for s in self.rot_spinners])
            
            # 更新缩放
            if hasattr(self, 'scale_spinners') and len(self.scale_spinners) == 3:
                self.current_geo.size = np.array([s.value() for s in self.scale_spinners])
        
        # 更新显示
        self.gl_widget.update()
    
    def _on_cancel(self):
        """取消按钮点击处理"""
        if not self.current_geo or not self.temp_data:
            return
            
        # 恢复原始数据
        with self._block_geo_signals():
            self.current_geo.name = self.temp_data['name']
            self.current_geo.position = self.temp_data['position']
            self.current_geo.rotation = self.temp_data['rotation']
            self.current_geo.size = self.temp_data['size']
            
            if hasattr(self.current_geo, 'material') and 'color' in self.temp_data:
                self.current_geo.material.color = self.temp_data['color']
        
        # 更新UI显示
        self.on_selection_changed(self.current_geo)
        
        # 更新3D视图
        self.gl_widget.update()
    
    def _create_spinbox(self, min_val=-999, max_val=999):
        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setSingleStep(0.1)
        spin.setMinimumWidth(100)
        return spin
        
    def _connect_signals(self):
        """连接所有控件的信号"""
        try:
            # 名称编辑框
            if hasattr(self, 'name_edit') and self.name_edit is not None:
                try:
                    self.name_edit.textChanged.disconnect()
                except:
                    pass
                self.name_edit.textChanged.connect(self._on_name_changed)
            
            # 位置spinners
            if hasattr(self, 'pos_spinners'):
                for spinner in self.pos_spinners:
                    if spinner is not None:
                        try:
                            spinner.valueChanged.disconnect()
                        except:
                            pass
                        spinner.valueChanged.connect(self._on_value_changed)
            
            # 旋转spinners
            if hasattr(self, 'rot_spinners'):
                for spinner in self.rot_spinners:
                    if spinner is not None:
                        try:
                            spinner.valueChanged.disconnect()
                        except:
                            pass
                        spinner.valueChanged.connect(self._on_value_changed)
            
            # 缩放spinners
            if hasattr(self, 'scale_spinners'):
                for spinner in self.scale_spinners:
                    if spinner is not None:
                        try:
                            spinner.valueChanged.disconnect()
                        except:
                            pass
                        spinner.valueChanged.connect(self._on_value_changed)
            
            # 颜色按钮
            if hasattr(self, 'color_button') and self.color_button is not None:
                try:
                    # 检查按钮是否有效
                    if not sip.isdeleted(self.color_button):
                        try:
                            self.color_button.clicked.disconnect()
                        except:
                            pass
                        self.color_button.clicked.connect(self._pick_color)
                except:
                    pass
                
        except Exception as e:
            print(f"连接信号时出错: {str(e)}")
            import traceback
            traceback.print_exc()
    
    @contextmanager
    def _block_signals(self):
        """信号阻断上下文管理器"""
        blockers = []
        
        # 在调用 clear_layout 前，清除所有控件引用
        # 这样可以避免引用已删除的控件
        if hasattr(self, 'form_layout') and self.form_layout.count() > 0:
            # 即将重建界面，先清除旧控件引用
            self.name_edit = None
            self.pos_spinners = []
            self.rot_spinners = []
            self.scale_spinners = []
            self.color_button = None
            self.roughness_slider = None
            self.metallic_slider = None
            self.visible_checkbox = None
        
        # 仅在存在对应控件时添加信号阻断器
        if hasattr(self, 'name_edit') and self.name_edit is not None:
            try:
                blockers.append(QSignalBlocker(self.name_edit))
            except RuntimeError:
                # 控件可能已被删除，忽略错误
                pass
        
        # 位置控件
        if hasattr(self, 'pos_spinners') and self.pos_spinners:
            for spin in self.pos_spinners:
                try:
                    blockers.append(QSignalBlocker(spin))
                except RuntimeError:
                    # 控件可能已被删除，忽略错误
                    pass
        
        # 旋转控件
        if hasattr(self, 'rot_spinners') and self.rot_spinners:
            for spin in self.rot_spinners:
                try:
                    blockers.append(QSignalBlocker(spin))
                except RuntimeError:
                    # 控件可能已被删除，忽略错误
                    pass
        
        # 缩放控件
        if hasattr(self, 'scale_spinners') and self.scale_spinners:
            for spin in self.scale_spinners:
                try:
                    blockers.append(QSignalBlocker(spin))
                except RuntimeError:
                    # 控件可能已被删除，忽略错误
                    pass
        
        try:
            yield
        finally:
            del blockers  # 确保退出作用域时解除阻断
            
    def _on_name_changed(self):
        """名称修改处理"""
        if not self.current_geo or self._in_update:
            return
        self.current_geo.name = self.name_edit.text()
        self.gl_widget.update()
        
    def _on_value_changed(self):
        """数值修改处理"""
        if not self.current_geo or self._in_update:
            return
            
        try:
            self._in_update = True
            # 原子化更新属性
            with self._block_geo_signals():
                # 更新位置
                if hasattr(self, 'pos_spinners') and self.pos_spinners:
                    self.current_geo.position = [
                        self.pos_spinners[0].value(),
                        self.pos_spinners[1].value(),
                        self.pos_spinners[2].value()
                    ]
                
                # 只有非组对象才更新这些属性
                if self.current_geo.type != "group":
                    # 更新旋转
                    if hasattr(self, 'rot_spinners') and self.rot_spinners:
                        self.current_geo.rotation = [
                            self.rot_spinners[0].value(),
                            self.rot_spinners[1].value(),
                            self.rot_spinners[2].value()
                        ]
                    
                    # 更新大小/缩放
                    if hasattr(self, 'scale_spinners') and self.scale_spinners:
                        self.current_geo.size = [
                            self.scale_spinners[0].value(),
                            self.scale_spinners[1].value(),
                            self.scale_spinners[2].value()
                        ]
        finally:
            self._in_update = False
            # 确保立即更新视图
            self.gl_widget.update()
            
    @contextmanager
    def _block_geo_signals(self):
        """阻断几何体信号"""
        if self.current_geo:
            blocker = QSignalBlocker(self.current_geo)
            try:
                yield
            finally:
                del blocker
        else:
            yield

    def _pick_color(self):
        if not hasattr(self, 'current_geo') or self.current_geo is None:
            return
        
        if not hasattr(self.current_geo, 'material'):
            return
        
        color = QColorDialog.getColor()
        if not color.isValid():
            return
        
        # 更新按钮样式
        if hasattr(self, 'color_button') and self.color_button is not None:
            self.color_button.setStyleSheet(f"background-color: {color.name()}")
        
        # 转换颜色值
        rgba = [color.redF(), color.greenF(), color.blueF(), color.alphaF()]
        self.current_geo.material.color = rgba
        self.gl_widget.update()

    def clear_layout(self, layout):
        """清除布局中的所有小部件"""
        if layout is None:
            return
            
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                # 递归清除子布局
                self.clear_layout(item.layout())
                item.layout().deleteLater()
    
    def _on_visibility_changed(self, checked):
        """处理可见性变更"""
        if not self.current_geo or self._in_update:
            return
        
        self.current_geo.visible = checked
        self.gl_widget.update()
