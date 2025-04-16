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
from Controlpanel import ControlPanel  # 假设ControlPanel在同一个包中的ControlPanel.py文件中

class GeometryType(OriginalGeometryType):
    if not hasattr(OriginalGeometryType, 'ELLIPSOID'):
        ELLIPSOID = 'ellipsoid'

if not hasattr(GeometryType, 'ELLIPSOID'):
    setattr(GeometryType, 'ELLIPSOID', 'ellipsoid')

class HierarchyTree(QDockWidget):
    """显示场景中几何体层次结构的树形控件"""
    def __init__(self, gl_widget):
        super().__init__("场景层次")
        self.gl_widget = gl_widget
        
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabel("场景对象")
        self.tree_widget.itemClicked.connect(self._on_item_clicked)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self._show_context_menu)
        
        # 创建工具栏
        toolbar = QToolBar()
        
        # 添加新组按钮
        self.add_group_action = QAction("添加组", self)
        self.add_group_action.triggered.connect(self._add_new_group)
        toolbar.addAction(self.add_group_action)
        
        # 删除按钮
        self.delete_action = QAction("删除", self)
        self.delete_action.triggered.connect(self._delete_selected)
        toolbar.addAction(self.delete_action)
        
        # 设置布局
        layout = QVBoxLayout()
        layout.addWidget(toolbar)
        layout.addWidget(self.tree_widget)
        
        container = QWidget()
        container.setLayout(layout)
        self.setWidget(container)
        
        # 对象和树项的映射
        self.obj_to_item = {}
        self.item_to_obj = {}  # 将使用 id(item) 作为键
        
        # 初始化刷新
        self.refresh()
        
        self._clipboard = None  # 添加剪贴板变量
    
    def refresh(self):
        """刷新整个树"""
        self.tree_widget.clear()
        self.obj_to_item = {}
        self.item_to_obj = {}
        
        # 获取顶层对象（未分组的几何体和顶层组）
        geometries = [geo for geo in self.gl_widget.geometries 
                     if geo.parent is None]
        
        # 添加所有顶层对象
        for geo in geometries:
            self._add_item_recursive(geo, self.tree_widget)
    
    def _add_item_recursive(self, obj, parent_item):
        """递归添加对象及其子对象到树"""
        # 创建树项
        if parent_item is self.tree_widget:
            # 顶层项
            item = QTreeWidgetItem(parent_item, [obj.name])
        else:
            # 子级项
            item = QTreeWidgetItem(parent_item, [obj.name])
        
        # 保存映射关系
        self.obj_to_item[obj] = item
        self.item_to_obj[id(item)] = obj
        
        # 设置图标
        if obj.type == "group":
            item.setIcon(0, QIcon("icons/folder.png"))  # 为目录设置文件夹图标
        else:
            # 为不同几何体类型设置不同图标
            icon_map = {
                GeometryType.BOX: "icons/cube.png",
                GeometryType.SPHERE: "icons/sphere.png",
                GeometryType.CYLINDER: "icons/cylinder.png",
                GeometryType.CAPSULE: "icons/capsule.png",
                GeometryType.PLANE: "icons/plane.png",
                GeometryType.ELLIPSOID: "icons/ellipsoid.png"
            }
            icon_path = icon_map.get(obj.type, "icons/shape.png")
            item.setIcon(0, QIcon(icon_path))
        
        # 如果是组，添加所有子对象
        if hasattr(obj, "children") and obj.children:
            for child in obj.children:
                self._add_item_recursive(child, item)
    
    def _on_item_clicked(self, item, column):
        """处理项点击事件，允许选择组和几何体"""
        obj = self.item_to_obj.get(id(item))
        if not obj:
            return
        
        # 检查是否按住Ctrl键
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.ControlModifier:
            # 直接调用set_selection，让原有的ctrl_press逻辑处理多选
            self.gl_widget.set_selection(obj)
        else:
            # 原有的单选逻辑
            self.gl_widget.set_selection(obj)
            
            # 展开或折叠组
            if obj.type == "group":
                if item.isExpanded():
                    item.setExpanded(False)
                else:
                    item.setExpanded(True)
    
    def update_selection(self, obj):
        """更新树形视图中的选中状态"""
        # 首先清除所有项的高亮
        iterator = QTreeWidgetItemIterator(self.tree_widget)  # 修改 self.tree 为 self.tree_widget
        while iterator.value():
            item = iterator.value()
            item.setBackground(0, QColor(255, 255, 255))  # 白色背景
            iterator += 1
            
        # 为所有选中的对象设置蓝色背景
        for selected_obj in self.gl_widget.selected_geos:
            self._update_selection_recursive(self.tree_widget.invisibleRootItem(), selected_obj)
    
    def _update_selection_recursive(self, item, obj):
        """递归更新选中状态"""
        # 检查当前项
        if hasattr(item, 'geo') and item.geo == obj:
            item.setBackground(0, QColor(173, 216, 230))  # 设置浅蓝色背景
            return True
            
        # 递归检查子项
        for i in range(item.childCount()):
            child = item.child(i)
            if self._update_selection_recursive(child, obj):
                return True
                
        return False
    
    def _show_context_menu(self, position):
        """显示上下文菜单"""
        item = self.tree_widget.itemAt(position)
        if not item:
            return
        
        obj = self.item_to_obj.get(id(item))
        if not obj:
            return

        menu = QMenu()
        
        # 检查是否是多选状态
        is_multi_select = len(self.gl_widget.selected_geos) > 1
        
        print(is_multi_select)

        # 复制操作
        copy_action = menu.addAction("复制")
        copy_action.triggered.connect(
            lambda: self._execute_multi_selection_action(self._copy_object) if is_multi_select 
            else self._copy_object(obj)
        )
        
        # 粘贴操作（仅当有复制内容且目标是组或根目录时可用）
        if hasattr(self, '_clipboard') and self._clipboard:
            paste_action = menu.addAction("粘贴")
            paste_action.triggered.connect(
                lambda: self._paste_object(obj)
            )
            # 只有组或根目录可以粘贴
            paste_action.setEnabled(obj.type == "group")
        
        menu.addSeparator()
        
        # 删除操作
        delete_action = menu.addAction("删除")
        delete_action.triggered.connect(
            lambda: self._execute_multi_selection_action(self._delete_object) if is_multi_select
            else self._delete_object(obj)
        )
        
        # 重命名操作（多选时禁用）
        rename_action = menu.addAction("重命名")
        rename_action.triggered.connect(lambda: self._rename_object(obj))
        rename_action.setEnabled(not is_multi_select)
        
        # 添加子对象的操作（仅对组对象可用，多选时禁用）
        if obj.type == "group" and not is_multi_select:
            menu.addSeparator()
            add_menu = menu.addMenu("添加")
            
            # 添加几何体
            geometry_types = {
                'BOX': GeometryType.BOX,
                'SPHERE': GeometryType.SPHERE,
                'CYLINDER': GeometryType.CYLINDER,
                'CAPSULE': GeometryType.CAPSULE,
                'PLANE': GeometryType.PLANE,
                'ELLIPSOID': GeometryType.ELLIPSOID
            }
            
            for name, geo_type in geometry_types.items():
                action = add_menu.addAction(name)
                action.triggered.connect(
                    lambda checked, t=geo_type: self._add_geometry_to_group(obj, t)
                )
            
            # 添加组
            add_menu.addSeparator()
            add_group_action = add_menu.addAction("组")
            add_group_action.triggered.connect(
                lambda: self._add_group_to_group(obj)
            )
        
        # 添加组合选项（仅在多选时显示）
        if is_multi_select:
            menu.addSeparator()
            combine_action = menu.addAction("组合所选对象")
            combine_action.triggered.connect(self._combine_selected_to_group)
        
        menu.exec_(self.tree_widget.viewport().mapToGlobal(position))

    def _combine_selected_to_group(self):
        """将选中的对象组合到一个新组中"""
        if len(self.gl_widget.selected_geos) <= 1:
            return
            
        # 创建新组
        new_group = GeometryGroup(name="Combined Group")
        
        # 获取所有选中对象的父组
        parents = []
        for obj in self.gl_widget.selected_geos:
            if obj.parent:
                parents.append(obj.parent)
            else:
                parents.append(self.gl_widget.geometries)
        
        # 如果所有对象都在同一个父组下，使用该父组
        # 否则添加到根级别
        common_parent = parents[0] if all(p == parents[0] for p in parents) else self.gl_widget.geometries
        
        # 从原位置移除对象并添加到新组
        for obj in self.gl_widget.selected_geos:
            if obj.parent:
                obj.parent.remove_child(obj)
            else:
                if obj in self.gl_widget.geometries:
                    self.gl_widget.geometries.remove(obj)
            new_group.add_child(obj)
        
        # 将新组添加到父组
        if isinstance(common_parent, list):
            common_parent.append(new_group)
        else:
            common_parent.add_child(new_group)
        
        # 更新选择为新组
        self.gl_widget.set_selection(new_group)
        
        # 刷新视图
        self.refresh()
        self.gl_widget.geometriesChanged.emit()
    
    def _copy_object(self, obj):
        """复制对象"""
        # 如果_clipboard已经是列表（多选复制），直接返回
        if isinstance(self._clipboard, list):
            return
            
        # 单个对象复制
        if isinstance(obj, Geometry):
            self._clipboard = Geometry(
                obj.type,
                name=f"Copy of {obj.name}",
                position=obj.position.copy(),
                size=obj.size.copy(),
                rotation=obj.rotation.copy()
            )
            # 复制材质属性
            self._clipboard.material.color = obj.material.color.copy()
        elif isinstance(obj, GeometryGroup):
            self._clipboard = self._deep_copy_group(obj)

    def _deep_copy_group(self, group):
        """深度复制组及其所有子对象"""
        new_group = GeometryGroup(
            name=f"Copy of {group.name}",
            position=group.position.copy(),
            rotation=group.rotation.copy()
        )
        
        # 递归复制所有子对象
        for child in group.children:
            if isinstance(child, Geometry):
                new_child = Geometry(
                    child.type,
                    name=f"Copy of {child.name}",
                    position=child.position.copy(),
                    size=child.size.copy(),
                    rotation=child.rotation.copy()
                )
                new_child.material.color = child.material.color.copy()
                new_group.add_child(new_child)
            elif isinstance(child, GeometryGroup):
                new_child = self._deep_copy_group(child)
                new_group.add_child(new_child)
                
        return new_group

    def _paste_object(self, target_obj):
        """粘贴对象到目标位置"""
        if not hasattr(self, '_clipboard') or self._clipboard is None:
            return
            
        # 处理多选复制的情况
        if isinstance(self._clipboard, list):
            for original_obj in self._clipboard:
                # 为每个对象创建副本
                if isinstance(original_obj, Geometry):
                    new_obj = Geometry(
                        original_obj.type,
                        name=f"Copy of {original_obj.name}",
                        position=original_obj.position.copy(),
                        size=original_obj.size.copy(),
                        rotation=original_obj.rotation.copy()
                    )
                    new_obj.material.color = original_obj.material.color.copy()
                else:  # GeometryGroup
                    new_obj = self._deep_copy_group(original_obj)
                    
                # 添加到目标位置
                if target_obj and target_obj.type == "group":
                    # 使用add_child而不是append，确保parent关系正确设置
                    target_obj.add_child(new_obj)
                else:
                    self.gl_widget.geometries.append(new_obj)
                    # 确保清除parent引用
                    new_obj.parent = None
        else:
            # 单个对象复制的情况
            if isinstance(self._clipboard, Geometry):
                new_obj = Geometry(
                    self._clipboard.type,
                    name=f"Copy of {self._clipboard.name}",
                    position=self._clipboard.position.copy(),
                    size=self._clipboard.size.copy(),
                    rotation=self._clipboard.rotation.copy()
                )
                new_obj.material.color = self._clipboard.material.color.copy()
            else:  # GeometryGroup
                new_obj = self._deep_copy_group(self._clipboard)
                
            # 添加到目标位置
            if target_obj and target_obj.type == "group":
                # 使用add_child而不是append，确保parent关系正确设置
                target_obj.add_child(new_obj)
            else:
                self.gl_widget.geometries.append(new_obj)
                # 确保清除parent引用
                new_obj.parent = None
        
        # 刷新视图
        self.refresh()
        self.gl_widget.geometriesChanged.emit()
    
    def _handle_context_action(self, action_data):
        """处理上下文菜单动作"""
        action_type = action_data[0]
        
        if action_type == "add_geo":
            # 添加几何体到组
            parent_group = action_data[1]
            geo_type = action_data[2]
            self._add_geometry_to_group(parent_group, geo_type)
        
        elif action_type == "add_group":
            # 添加子组
            parent_group = action_data[1]
            self._add_group_to_group(parent_group)
        
        elif action_type == "rename":
            # 重命名对象
            obj = action_data[1]
            self._rename_object(obj)
        
        elif action_type == "delete":
            # 删除对象
            obj = action_data[1]
            self._delete_object(obj)
    
    def _add_geometry_to_group(self, parent_group, geo_type):
        """添加几何体到组内
        
        Args:
            parent_group: 父级组对象
            geo_type: 几何体类型
        """
        try:
            # 创建几何体实例
            count = len(parent_group.children) + 1
            name = f"{geo_type}_{count}"
            
            # 创建几何体对象
            geo = Geometry(
                geo_type=geo_type,
                name=name,
                position=(0, 0, 0),
                size=(1, 1, 1),
                rotation=(0, 0, 0)
            )
            print(2,geo.name)
            self.gl_widget.add_geometry(geo,parent_group)
            # self.gl_widget.geometries.append(geo)

            
            # 刷新层级树
            self.refresh()
            
            # 选中新添加的几何体
            self.gl_widget.set_selection(geo)
            
            # 确保更新组的变换矩阵，传递给子对象
            if hasattr(self.gl_widget, 'update_transforms_recursive'):
                self.gl_widget.update_transforms_recursive(parent_group)
            
            # 如果在观察模式，自动切换到平移模式
            if self.gl_widget.current_mode == OperationMode.MODE_OBSERVE:
                for panel in self.gl_widget.parent().findChildren(ControlPanel):
                    if hasattr(panel, 'translate_btn'):
                        panel.translate_btn.setChecked(True)
                        break
            
            # 更新视图
            self.gl_widget.update()
        except Exception as e:
            print(f"向组添加几何体时出错: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _add_group_to_group(self, parent_group):
        """添加子组到父组"""
        # 创建新组
        new_group = GeometryGroup(
            name="New Group",
            position=(0, 0, 0)
        )
        
        # 添加到父组
        parent_group.add_child(new_group)
        
        # 更新UI
        self.refresh()
        self.gl_widget.update()
    
    def _add_new_group(self):
        """添加新的顶层组"""
        # 创建新组
        new_group = GeometryGroup(
            name="New Group",
            position=(0, 0, 0)
        )
        
        # 添加到场景
        self.gl_widget.geometries.append(new_group)
        
        # 更新UI
        self.refresh()
        self.gl_widget.update()
    
    def _rename_object(self, obj):
        """重命名对象"""
        new_name, ok = QInputDialog.getText(
            self, "重命名", "输入新名称:", 
            QLineEdit.Normal, obj.name
        )
        
        if ok and new_name:
            obj.name = new_name
            
            # 更新UI
            item = self.obj_to_item.get(obj)
            if item:
                item.setText(0, new_name)
    
    def _delete_object(self, obj):
        """删除对象"""
        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确定要删除 '{obj.name}' 吗?",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 如果正在被选中，先取消选择
            if self.gl_widget.selected_geo == obj:
                self.gl_widget.set_selection(None)
            
            # 根据对象类型和位置进行删除
            if obj.parent:
                try:
                    # 使用remove_child方法从父组中移除
                    if hasattr(obj.parent, 'remove_child'):
                        obj.parent.remove_child(obj)
                    else:
                        # 如果没有remove_child方法，直接从children列表移除
                        if obj in obj.parent.children:
                            obj.parent.children.remove(obj)
                            # 手动清除parent引用
                            obj.parent = None
                except Exception as e:
                    print(f"从父组中移除对象时出错: {str(e)}")
                    # 如果出错，尝试直接移除
                    if obj in obj.parent.children:
                        obj.parent.children.remove(obj)
                        obj.parent = None
            else:
                # 从场景根级别移除
                if obj in self.gl_widget.geometries:
                    self.gl_widget.geometries.remove(obj)
            
            # 更新UI
            self.refresh()
            self.gl_widget.update()
    
    def _delete_selected(self):
        """删除当前选中的对象"""
        selected_items = self.tree_widget.selectedItems()
        if not selected_items:
            return
            
        item = selected_items[0]
        obj = self.item_to_obj.get(item)
        if obj:
            self._delete_object(obj)

    def _handle_copy_shortcut(self):
        """处理复制快捷键"""
        if self.gl_widget.selected_geo:
            self._copy_object(self.gl_widget.selected_geo)
            
    def _handle_paste_shortcut(self):
        """处理粘贴快捷键"""
        if self._clipboard is not None:
            self._paste_object(None)  # 粘贴到根级别

    def _execute_multi_selection_action(self, action_func, *args):
        """
        对所有选中的对象执行指定操作
        action_func: 要执行的操作函数
        args: 传递给操作函数的参数
        """
        if not self.gl_widget.selected_geos:
            return
                
        # 复制操作：存储所有选中对象的引用
        if action_func == self._copy_object:
            self._clipboard = self.gl_widget.selected_geos.copy()
            return
                
        # 粘贴操作：先创建所有副本，然后再添加到目标位置
        if action_func == self._paste_object:
            target_obj = args[0] if args else None
            if hasattr(self, '_clipboard') and self._clipboard:
                # 先创建所有对象的深度副本
                copies = []
                for obj in self._clipboard:
                    if isinstance(obj, Geometry):
                        copy = Geometry(
                            obj.type,
                            name=f"Copy of {obj.name}",
                            position=obj.position.copy(),
                            size=obj.size.copy(),
                            rotation=obj.rotation.copy()
                        )
                        copy.material.color = obj.material.color.copy()
                        copies.append(copy)
                    elif isinstance(obj, GeometryGroup):
                        copies.append(self._deep_copy_group(obj))
                
                # 然后将所有副本添加到目标位置
                for copy in copies:
                    if target_obj:
                        if isinstance(target_obj, GeometryGroup):
                            target_obj.add_child(copy)
                        else:
                            # 如果目标不是组，添加到父组
                            parent = target_obj.parent or self.gl_widget.geometries
                            parent.add_child(copy)
                    else:
                        # 没有目标对象时添加到根级别
                        self.gl_widget.geometries.append(copy)
                
                # 刷新视图
                self.refresh()
                self.gl_widget.geometriesChanged.emit()
            return
                
        # 删除操作：直接逐个删除
        if action_func == self._delete_object:
            for obj in self.gl_widget.selected_geos:
                self._delete_object(obj)
            return
                
        # 其他操作：逐个执行
        for obj in self.gl_widget.selected_geos:
            action_func(obj, *args)
