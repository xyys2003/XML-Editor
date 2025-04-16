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
import copy
import json
import os
from datetime import datetime



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
        
        # 添加状态保存器组
        self.state_group = QGroupBox("状态管理")
        self.state_layout = QVBoxLayout()
        self.state_group.setLayout(self.state_layout)
        
        # 添加状态保存和加载按钮
        self.save_state_button = QPushButton("保存当前状态")
        self.save_state_button.clicked.connect(self._save_current_state)
        self.state_layout.addWidget(self.save_state_button)
        
        # 创建状态列表
        self.state_list = QListWidget()
        self.state_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.state_list.itemDoubleClicked.connect(self._load_selected_state)
        self.state_layout.addWidget(self.state_list)
        
        # 添加加载和删除按钮
        load_delete_layout = QHBoxLayout()
        self.load_state_button = QPushButton("加载")
        self.load_state_button.clicked.connect(self._load_selected_state)
        self.delete_state_button = QPushButton("删除")
        self.delete_state_button.clicked.connect(self._delete_selected_state)
        load_delete_layout.addWidget(self.load_state_button)
        load_delete_layout.addWidget(self.delete_state_button)
        self.state_layout.addLayout(load_delete_layout)
        
        # 将状态管理组添加到主布局
        self.main_layout.addWidget(self.state_group)
        
        # 连接按钮信号
        self.apply_button.clicked.connect(self._on_apply)
        self.cancel_button.clicked.connect(self._on_cancel)
        
        # 存储临时数据的变量
        self.temp_data = {}
        
        # 初始化状态保存列表和状态数据
        self.states = []
        self.max_states = 50  # 最大保存状态数
        self._load_saved_states()  # 加载已保存的状态
        
        self.setWidget(self.main_widget)
        
    def on_selection_changed(self, geo):
        """当选择变更时更新面板内容"""
        self.current_geo = geo  # 更新当前几何体引用
        self._in_update = True  # 设置更新标志
        
        try:
            # 在调用 clear_layout 前，清除所有控件引用
            # 这样可以避免引用已删除的控件
            if hasattr(self, 'form_layout') and self.form_layout.count() > 0:
                # 即将重建界面，先清除旧控件引用
                self.name_edit = None
                self.pos_spinners = []
                self.rot_spinners = []
                self.scale_spinners = []
                self.color_button = None
                self.color_preview = None  # 如果有颜色预览控件
            
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
                # 确保临时颜色变量初始化
                self.temp_color = geo.material.color.copy()
            
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
                # 创建颜色选择区域
                color_widget = QWidget()
                color_layout = QHBoxLayout()
                color_widget.setLayout(color_layout)
                
                # 添加颜色显示区域
                self.color_preview = QFrame()
                self.color_preview.setFixedSize(30, 30)
                self.color_preview.setFrameShape(QFrame.Box)
                self.color_preview.setFrameShadow(QFrame.Plain)
                
                # 设置当前颜色
                color = geo.material.color
                self.color_preview.setStyleSheet(
                    f"background-color: rgb({int(color[0]*255)}, {int(color[1]*255)}, {int(color[2]*255)}); border: 1px solid #888;")
                
                # 添加颜色选择按钮
                self.color_button = QPushButton("选择颜色")
                self.color_button.setFixedHeight(30)
                
                # 添加到布局
                color_layout.addWidget(self.color_preview)
                color_layout.addWidget(self.color_button)
                
                self.form_layout.addRow("颜色:", color_widget)
                
                # 添加颜色预设面板
                preset_widget = QWidget()
                preset_layout = QHBoxLayout()
                preset_layout.setSpacing(2)
                preset_widget.setLayout(preset_layout)
                
                # 定义预设颜色
                presets = [
                    ((1.0, 0.0, 0.0), "红色"),
                    ((0.0, 1.0, 0.0), "绿色"),
                    ((0.0, 0.0, 1.0), "蓝色"),
                    ((1.0, 1.0, 0.0), "黄色"),
                    ((1.0, 0.0, 1.0), "紫色"),
                    ((0.0, 1.0, 1.0), "青色"),
                    ((0.5, 0.5, 0.5), "灰色"),
                    ((1.0, 1.0, 1.0), "白色")
                ]
                
                # 创建颜色按钮
                for preset_color, tooltip in presets:
                    btn = QPushButton()
                    btn.setFixedSize(20, 20)
                    btn.setToolTip(tooltip)
                    btn.setStyleSheet(
                        f"background-color: rgb({int(preset_color[0]*255)}, "
                        f"{int(preset_color[1]*255)}, {int(preset_color[2]*255)}); "
                        f"border: 1px solid #888;")
                    # 使用闭包保存颜色值
                    btn.clicked.connect(lambda checked, c=preset_color: self._apply_preset_color(c))
                    preset_layout.addWidget(btn)
                
                self.form_layout.addRow("预设:", preset_widget)
            
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
            
            # 更新颜色（如果已选择）
            if hasattr(self, 'temp_color') and hasattr(self.current_geo, 'material'):
                self.current_geo.material.color = self.temp_color
        
        # 更新显示
        self.gl_widget.update()
        
        # 更新临时数据，使其与当前应用的值一致
        self.temp_data = {
            'name': self.current_geo.name,
            'position': self.current_geo.position.copy(),
            'rotation': self.current_geo.rotation.copy(),
            'size': self.current_geo.size.copy()
        }
        
        if hasattr(self.current_geo, 'material'):
            self.temp_data['color'] = self.current_geo.material.color.copy()
    
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
            
            # 位置spinners
            if hasattr(self, 'pos_spinners'):
                for spinner in self.pos_spinners:
                    if spinner is not None:
                        try:
                            spinner.valueChanged.disconnect()
                        except:
                            pass
            
            # 旋转spinners
            if hasattr(self, 'rot_spinners'):
                for spinner in self.rot_spinners:
                    if spinner is not None:
                        try:
                            spinner.valueChanged.disconnect()
                        except:
                            pass
            
            # 缩放spinners
            if hasattr(self, 'scale_spinners'):
                for spinner in self.scale_spinners:
                    if spinner is not None:
                        try:
                            spinner.valueChanged.disconnect()
                        except:
                            pass
            
            # 颜色按钮 - 需保留颜色选择功能，但选择后不立即应用
            if hasattr(self, 'color_button') and self.color_button is not None:
                try:
                    import sip
                    if not sip.isdeleted(self.color_button):
                        try:
                            self.color_button.clicked.disconnect()
                        except:
                            pass
                        self.color_button.clicked.connect(self._pick_color_preview)  # 修改为预览方法
                except ImportError:
                    try:
                        self.color_button.objectName()
                        self.color_button.clicked.disconnect()
                        self.color_button.clicked.connect(self._pick_color_preview)  # 修改为预览方法
                    except RuntimeError:
                        print("警告: 颜色按钮可能已被删除，跳过信号连接")
                        pass
            
            # 颜色预览区域点击也可以打开颜色选择器
            if hasattr(self, 'color_preview') and self.color_preview is not None:
                self.color_preview.mousePressEvent = lambda event: self._pick_color_preview()  # 修改为预览方法
                self.color_preview.setCursor(Qt.PointingHandCursor)
                
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
                
                # 只有非组对象才直接更新这些属性
                if not hasattr(self.current_geo, 'type') or self.current_geo.type != "group":
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
                else:
                    # 组对象需要特殊处理
                    # 旋转属性可以直接更新
                    if hasattr(self, 'rot_spinners') and self.rot_spinners:
                        self.current_geo.rotation = [
                            self.rot_spinners[0].value(),
                            self.rot_spinners[1].value(),
                            self.rot_spinners[2].value()
                        ]
                    
                    # 缩放属性需要应用组缩放逻辑
                    if hasattr(self, 'scale_spinners') and self.scale_spinners and hasattr(self, 'temp_data'):
                        # 获取原始尺寸和新尺寸（添加安全检查）
                        old_size = np.array(self.temp_data.get('size', [1.0, 1.0, 1.0]))
                        new_size = np.array([
                            self.scale_spinners[0].value(),
                            self.scale_spinners[1].value(),
                            self.scale_spinners[2].value()
                        ])
                        
                        # 防止除零错误和无效值
                        scale_factors = np.ones(3)  # 默认不缩放
                        for i in range(3):
                            # 确保旧尺寸不为零
                            if abs(old_size[i]) > 0.0001:
                                scale_factors[i] = new_size[i] / old_size[i]
                            else:
                                # 如果旧尺寸接近零，使用新尺寸作为绝对值
                                scale_factors[i] = 1.0  # 不缩放
                                # 如果新尺寸有效，则直接设置
                                if new_size[i] > 0.0001:
                                    self.current_geo.size[i] = new_size[i]
                        
                        # 对组应用缩放逻辑
                        for i in range(3):
                            # 检查哪些维度需要缩放
                            if abs(scale_factors[i] - 1.0) > 0.0001 and np.isfinite(scale_factors[i]):  # 确保是有限值
                                # 创建缩放方向向量
                                scale_direction = [0, 0, 0]
                                scale_direction[i] = 1
                                
                                # 应用组缩放逻辑
                                if hasattr(self.gl_widget, '_scale_group_recursive'):
                                    self.gl_widget._scale_group_recursive(
                                        self.current_geo,
                                        self.current_geo.position,
                                        scale_factors[i],
                                        scale_direction
                                    )
                        
                        # 更新临时数据中的尺寸，以便下次计算缩放因子
                        self.temp_data['size'] = new_size.tolist()
                        
                        # 设置组的尺寸属性
                        self.current_geo.size = new_size
        except Exception as e:
            print(f"更新属性时出错: {str(e)}")
            import traceback
            traceback.print_exc()
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

    def _pick_color_preview(self):
        """打开颜色选择器但仅预览颜色，不立即应用到几何体"""
        if not hasattr(self, 'current_geo') or self.current_geo is None:
            return
        
        if not hasattr(self.current_geo, 'material'):
            return
        
        # 获取当前颜色
        current_color = self.current_geo.material.color
        
        # 创建QColor对象
        initial_color = QColor(
            int(current_color[0] * 255),
            int(current_color[1] * 255),
            int(current_color[2] * 255)
        )
        
        # 打开颜色选择器
        color = QColorDialog.getColor(initial=initial_color)
        if not color.isValid():
            return
        
        # 仅更新预览，不应用到几何体
        if hasattr(self, 'color_preview') and self.color_preview is not None:
            self.color_preview.setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid #888;")
        
        # 保存颜色值到临时数据
        self.temp_color = [color.redF(), color.greenF(), color.blueF(), 1.0]

    def _apply_preset_color(self, color_rgb):
        """应用预设颜色到预览，但不立即应用到几何体"""
        if not self.current_geo or not hasattr(self.current_geo, 'material'):
            return
        
        # 创建QColor对象
        qcolor = QColor(
            int(color_rgb[0] * 255),
            int(color_rgb[1] * 255),
            int(color_rgb[2] * 255)
        )
        
        # 仅更新预览
        if hasattr(self, 'color_preview') and self.color_preview is not None:
            self.color_preview.setStyleSheet(
                f"background-color: {qcolor.name()}; border: 1px solid #888;")
        
        # 保存颜色值到临时数据
        self.temp_color = [qcolor.redF(), qcolor.greenF(), qcolor.blueF(), 1.0]

    def clear_layout(self, layout):
        """清除布局中的所有小部件，确保它们被正确删除"""
        if layout is None:
            return
            
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            
            if widget is not None:
                widget.setParent(None)  # 先解除父子关系
                widget.deleteLater()    # 安排在事件循环中删除
            elif item.layout() is not None:
                # 递归清除子布局
                self.clear_layout(item.layout())
                item.layout().setParent(None)  # 解除父子关系
    
    def _on_visibility_changed(self, checked):
        """处理可见性变更"""
        if not self.current_geo or self._in_update:
            return
        
        self.current_geo.visible = checked
        self.gl_widget.update()

    def _save_current_state(self):
        """保存当前场景的所有几何体状态"""
        if not self.gl_widget.geometries:
            QMessageBox.warning(self, "保存失败", "当前场景中没有几何体对象，无法保存状态。")
            return
            
        try:
            # 保存时间戳
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 创建几何体状态副本
            geometries_copy = self._serialize_geometries(self.gl_widget.geometries)
            
            # 保存摄像机状态
            camera_config = {}
            if hasattr(self.gl_widget, 'get_camera_config'):
                # 检查方法是否需要参数
                import inspect
                sig = inspect.signature(self.gl_widget.get_camera_config)
                if len(sig.parameters) == 0:
                    camera_config = self.gl_widget.get_camera_config()
                else:
                    print("相机配置方法需要参数，跳过获取相机状态")
            else:
                # 手动构建相机配置
                for attr in ['camera_position', 'camera_target', 'camera_up', 'fov', 'near_plane', 'far_plane']:
                    if hasattr(self.gl_widget, attr):
                        value = getattr(self.gl_widget, attr)
                        if isinstance(value, np.ndarray):
                            camera_config[attr] = value.tolist()
                        else:
                            camera_config[attr] = value
            
            # 创建完整状态字典
            state = {
                'timestamp': timestamp,
                'geometries': geometries_copy,
                'camera': camera_config
            }
            
            # 添加到状态列表
            self.states.append(state)
            
            # 如果超过最大状态数，删除最早的状态
            while len(self.states) > self.max_states:
                self.states.pop(0)
            
            # 更新状态列表UI
            self._update_state_list()
            
            # 保存状态到文件
            self._save_states_to_file()
            
            QMessageBox.information(self, "保存成功", f"场景状态已保存: {timestamp}")
        except Exception as e:
            import traceback
            error_message = f"保存状态时发生错误:\n{str(e)}"
            print(error_message)
            traceback.print_exc()
            QMessageBox.critical(self, "保存失败", error_message)
        
    def _load_selected_state(self):
        """加载选中的状态"""
        selected_items = self.state_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "加载失败", "请先选择一个状态。")
            return
            
        # 获取选中的索引
        index = self.state_list.row(selected_items[0])
        if index < 0 or index >= len(self.states):
            return
            
        # 确认是否加载
        reply = QMessageBox.question(
            self, 
            "加载状态", 
            "加载状态将覆盖当前场景所有几何体，确定继续吗？",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
            
        try:
            # 加载状态
            selected_state = self.states[index]
            
            # 清除当前几何体
            self.gl_widget.geometries.clear()
            
            # 反序列化并加载几何体
            geometries = self._deserialize_geometries(selected_state['geometries'])
            for geo in geometries:
                self.gl_widget.add_geometry(geo)
            
            # 恢复摄像机状态（检查方法是否存在并且能接受参数）
            if 'camera' in selected_state:
                camera_config = selected_state['camera']
                # 检查方法是否存在
                if hasattr(self.gl_widget, 'update_camera_config'):
                    # 检查方法是否能接受参数
                    import inspect
                    sig = inspect.signature(self.gl_widget.update_camera_config)
                    if len(sig.parameters) > 0:
                        # 方法能接受参数
                        self.gl_widget.update_camera_config(camera_config)
                    else:
                        # 方法不接受参数，但我们可以手动设置属性
                        print("相机配置方法不接受参数，尝试直接设置属性...")
                        for key, value in camera_config.items():
                            if hasattr(self.gl_widget, key):
                                try:
                                    setattr(self.gl_widget, key, value)
                                except:
                                    print(f"无法设置相机属性: {key}")
            
            # 更新视图
            self.gl_widget.update()
            
            # 清除当前选中状态
            self.gl_widget.set_selection(None)
            self.on_selection_changed(None)
            
            QMessageBox.information(self, "加载成功", f"场景状态已加载: {selected_state['timestamp']}")
        except Exception as e:
            error_message = f"加载状态失败: {str(e)}"
            print(error_message)
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "加载失败", error_message)
        
    def _delete_selected_state(self):
        """删除选中的状态"""
        selected_items = self.state_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "删除失败", "请先选择一个状态。")
            return
            
        # 获取选中的索引
        index = self.state_list.row(selected_items[0])
        if index < 0 or index >= len(self.states):
            return
            
        # 确认是否删除
        reply = QMessageBox.question(
            self, 
            "删除状态", 
            "确定要删除选中的状态吗？此操作无法恢复。",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
            
        # 删除状态
        removed_state = self.states.pop(index)
        
        # 更新状态列表UI
        self._update_state_list()
        
        # 保存更新后的状态列表
        self._save_states_to_file()
        
        QMessageBox.information(self, "删除成功", f"已删除状态: {removed_state['timestamp']}")
        
    def _update_state_list(self):
        """更新状态列表UI"""
        self.state_list.clear()
        for state in reversed(self.states):  # 显示最新的在前面
            item = QListWidgetItem(state['timestamp'])
            # 添加几何体数量提示
            geo_count = len(state['geometries'])
            item.setToolTip(f"包含 {geo_count} 个几何体对象")
            self.state_list.addItem(item)
            
    def _serialize_geometries(self, geometries):
        """将几何体对象序列化为可存储的格式"""
        serialized = []
        
        for geo in geometries:
            if hasattr(geo, 'type') and geo.type == "group":
                # 处理组对象
                group_data = {
                    'type': 'group',
                    'name': geo.name,
                    'position': geo.position.tolist() if isinstance(geo.position, np.ndarray) else geo.position,
                    'rotation': geo.rotation.tolist() if isinstance(geo.rotation, np.ndarray) else geo.rotation,
                    'size': geo.size.tolist() if isinstance(geo.size, np.ndarray) else geo.size
                }
                
                # 只有当有子对象时才添加子对象列表
                if hasattr(geo, 'children'):
                    group_data['children'] = self._serialize_geometries(geo.children)
                else:
                    group_data['children'] = []
                    
                # 检查可见性属性（如果存在）
                if hasattr(geo, 'visible'):
                    group_data['visible'] = geo.visible
                
                serialized.append(group_data)
            else:
                # 处理普通几何体
                serialized_geo = {
                    'geo_type': geo.type,
                    'name': geo.name,
                    'position': geo.position.tolist() if isinstance(geo.position, np.ndarray) else geo.position,
                    'rotation': geo.rotation.tolist() if isinstance(geo.rotation, np.ndarray) else geo.rotation,
                    'size': geo.size.tolist() if isinstance(geo.size, np.ndarray) else geo.size
                }
                
                # 检查可见性属性（如果存在）
                if hasattr(geo, 'visible'):
                    serialized_geo['visible'] = geo.visible
                
                # 添加材质属性（如果有）
                if hasattr(geo, 'material'):
                    material_data = {}
                    
                    if hasattr(geo.material, 'color'):
                        material_data['color'] = geo.material.color.tolist() if isinstance(geo.material.color, np.ndarray) else geo.material.color
                    
                    # 安全获取附加材质属性
                    for prop in ['roughness', 'metallic', 'shininess']:
                        if hasattr(geo.material, prop):
                            material_data[prop] = getattr(geo.material, prop)
                    
                    # 处理特殊的numpy数组属性
                    if hasattr(geo.material, 'specular') and getattr(geo.material, 'specular') is not None:
                        material_data['specular'] = geo.material.specular.tolist() if isinstance(geo.material.specular, np.ndarray) else geo.material.specular
                    
                    serialized_geo['material'] = material_data
                    
                serialized.append(serialized_geo)
                
        return serialized
        
    def _deserialize_geometries(self, serialized):
        """从序列化数据还原几何体对象"""
        geometries = []
        
        for data in serialized:
            if data.get('type') == 'group':
                # 创建组对象
                try:
                    group = GeometryGroup(
                        name=data['name'],
                        position=np.array(data['position']),
                        rotation=np.array(data['rotation'])
                    )
                    
                    # 安全设置大小，如果有的话
                    if 'size' in data:
                        group.size = np.array(data['size'])
                    
                    # 设置可见性（如果数据中有且对象支持）
                    if 'visible' in data and hasattr(group, 'visible'):
                        group.visible = data['visible']
                    
                    # 递归添加子对象
                    children = self._deserialize_geometries(data.get('children', []))
                    for child in children:
                        group.add_child(child)
                        
                    geometries.append(group)
                except Exception as e:
                    print(f"创建组对象失败: {str(e)}")
                    print(f"组数据: {data}")
                    continue
            else:
                # 创建普通几何体
                try:
                    geo = Geometry(
                        geo_type=data['geo_type'],
                        name=data['name'],
                        position=np.array(data['position']),
                        rotation=np.array(data['rotation']),
                        size=np.array(data['size'])
                    )
                    
                    # 设置可见性（如果数据中有且对象支持）
                    if 'visible' in data and hasattr(geo, 'visible'):
                        geo.visible = data['visible']
                    
                    # 还原材质（如果有）
                    if 'material' in data and hasattr(geo, 'material'):
                        # 安全设置材质属性
                        if 'color' in data['material']:
                            geo.material.color = np.array(data['material']['color'])
                        
                        # 设置其他可能的材质属性
                        material_props = ['roughness', 'metallic', 'shininess']
                        for prop in material_props:
                            if prop in data['material'] and hasattr(geo.material, prop):
                                setattr(geo.material, prop, data['material'][prop])
                        
                        # 处理颜色数组属性
                        if 'specular' in data['material'] and hasattr(geo.material, 'specular'):
                            geo.material.specular = np.array(data['material']['specular'])
                            
                    geometries.append(geo)
                except Exception as e:
                    print(f"创建几何体失败: {str(e)}")
                    print(f"几何体数据: {data}")
                    continue
                
        return geometries
    
    def _save_states_to_file(self):
        """将状态保存到文件"""
        try:
            # 确保目录存在
            save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saved_states')
            os.makedirs(save_dir, exist_ok=True)
            
            # 保存状态到文件，使用自定义编码器处理numpy数组
            save_path = os.path.join(save_dir, 'saved_states.json')
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self.states, f, ensure_ascii=False, indent=2, cls=NumpyJSONEncoder)
                
        except Exception as e:
            print(f"保存状态到文件失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _load_saved_states(self):
        """从文件加载已保存的状态"""
        try:
            save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saved_states')
            save_path = os.path.join(save_dir, 'saved_states.json')
            
            if os.path.exists(save_path):
                with open(save_path, 'r', encoding='utf-8') as f:
                    self.states = json.load(f)
                    
                # 将旧版本的状态数据转换为新格式
                for state in self.states:
                    if 'camera' not in state:
                        # 添加默认摄像机配置
                        state['camera'] = {
                            'position': [5, 5, 5],
                            'target': [0, 0, 0],
                            'up': [0, 1, 0],
                            'fov': 45.0,
                            'near': 0.1,
                            'far': 1000.0
                        }
                        
                # 限制状态数量
                while len(self.states) > self.max_states:
                    self.states.pop(0)
                    
                # 更新状态列表UI
                self._update_state_list()
                
        except Exception as e:
            print(f"加载保存的状态失败: {str(e)}")
            # 初始化为空列表
            self.states = []

class NumpyJSONEncoder(json.JSONEncoder):
    """处理numpy数组JSON序列化的自定义编码器"""
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        return super().default(obj)
