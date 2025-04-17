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
class XMLParser:
    @staticmethod
    def load(filename):
        """
        从XML文件导入几何体和组层级结构，保持与export_enhanced_xml导出格式兼容
        """
        try:
            tree = ET.parse(filename)
            root = tree.getroot()
            geometries = []
            
            # 检查文件格式类型
            is_mujoco_format = root.tag == "mujoco"
            is_enhanced_format = root.tag == "Scene"
            
            if is_enhanced_format:
                # 处理增强格式的XML（对应export_enhanced_xml方法）
                objects_node = root.find("Objects")
                if objects_node is not None:
                    # 递归处理对象树
                    def process_node(node, parent=None):
                        results = []
                        
                        for child in node:
                            if child.tag == "Group":
                                # 创建组
                                name = child.get("name", "Group")
                                
                                # 解析位置
                                pos_elem = child.find("Position")
                                position = [0, 0, 0]
                                if pos_elem is not None:
                                    position = [
                                        float(pos_elem.get("x", 0)),
                                        float(pos_elem.get("y", 0)),
                                        float(pos_elem.get("z", 0))
                                    ]
                                
                                # 解析旋转
                                rot_elem = child.find("Rotation")
                                rotation = [0, 0, 0]
                                if rot_elem is not None:
                                    rotation = [
                                        float(rot_elem.get("x", 0)),
                                        float(rot_elem.get("y", 0)),
                                        float(rot_elem.get("z", 0))
                                    ]
                                
                                # 创建组对象
                                group = GeometryGroup(name=name, position=position, rotation=rotation, parent=parent)
                                
                                # 处理子节点
                                children_elem = child.find("Children")
                                if children_elem is not None:
                                    child_objects = process_node(children_elem, group)
                                    for child_obj in child_objects:
                                        if parent is None:  # 顶层对象
                                            group.add_child(child_obj)
                                
                                if parent is None:
                                    results.append(group)
                                else:
                                    parent.add_child(group)
                                
                            elif child.tag == "Geometry":
                                # 处理几何体
                                name = child.get("name", "Object")
                                geo_type = child.get("type", "box")
                                
                                # 解析位置
                                pos_elem = child.find("Position")
                                position = [0, 0, 0]
                                if pos_elem is not None:
                                    position = [
                                        float(pos_elem.get("x", 0)),
                                        float(pos_elem.get("y", 0)),
                                        float(pos_elem.get("z", 0))
                                    ]
                                    
                                # 解析尺寸
                                size_elem = child.find("Size")
                                size = [1, 1, 1]
                                if size_elem is not None:
                                    size = [
                                        float(size_elem.get("x", 1)),
                                        float(size_elem.get("y", 1)),
                                        float(size_elem.get("z", 1))
                                    ]
                                    
                                # 解析旋转
                                rot_elem = child.find("Rotation")
                                rotation = [0, 0, 0]
                                if rot_elem is not None:
                                    rotation = [
                                        float(rot_elem.get("x", 0)),
                                        float(rot_elem.get("y", 0)),
                                        float(rot_elem.get("z", 0))
                                    ]
                                
                                # 创建几何体
                                geo = Geometry(
                                    geo_type=geo_type, 
                                    name=name,
                                    position=position,
                                    size=size,
                                    rotation=rotation,
                                    parent=parent
                                )
                                
                                # 处理材质
                                material_elem = child.find("Material")
                                if material_elem is not None:
                                    color_elem = material_elem.find("Color")
                                    if color_elem is not None:
                                        color = [
                                            float(color_elem.get("r", 1.0)),
                                            float(color_elem.get("g", 1.0)),
                                            float(color_elem.get("b", 1.0)),
                                            float(color_elem.get("a", 1.0))
                                        ]
                                        geo.material.color = color
                                
                                if parent is None:
                                    results.append(geo)
                                else:
                                    parent.add_child(geo)
                        
                        return results
                    
                    # 开始处理对象节点
                    geometries = process_node(objects_node)
                    
            elif is_mujoco_format:
                # 处理MuJoCo格式的XML
                # 同您已经实现的部分逻辑，但需要处理子节点关系
                
                # 创建一个字典来跟踪body和对应的几何体组
                body_groups = {}
                parent_map = {}  # 用于跟踪父子关系
                
                # 构建父子关系映射
                for body in root.findall(".//body"):
                    body_name = body.get('name', 'Unnamed')
                    # 寻找直接父body
                    parent_body = None
                    for parent in root.findall(".//body"):
                        if body in parent.findall("./body"):
                            parent_body = parent
                            break
                    
                    if parent_body is not None:
                        parent_map[body_name] = parent_body.get('name', 'Unnamed')
                
                # 处理所有body
                for body in root.findall(".//body"):
                    body_name = body.get('name', 'Unnamed')
                    if body_name in body_groups:
                        continue  # 跳过已处理的body
                    
                    body_pos = list(map(float, body.get('pos', '0 0 0').split()))
                    body_euler = list(map(float, body.get('euler', '0 0 0').split())) if 'euler' in body.attrib else [0, 0, 0]
                    
                    # 创建组对象
                    group = GeometryGroup(
                        name=body_name,
                        position=body_pos,
                        rotation=body_euler
                    )
                    body_groups[body_name] = group
                    
                    # 添加所有geom子对象
                    for geom in body.findall("geom"):
                        geo_type = geom.get('type', 'box')
                        geom_name = geom.get('name', f"{body_name}_geom")
                        
                        # 解析尺寸
                        size_str = geom.get('size', '1 1 1')
                        size = list(map(float, size_str.split()))
                        
                        # 调整尺寸格式，参考导出逻辑
                        if geo_type == 'sphere':
                            if len(size) == 1:
                                size = [size[0], size[0], size[0]]  # 球体使用相同的三个半径
                        elif geo_type == 'ellipsoid':
                            # 确保有三个尺寸
                            if len(size) < 3:
                                size.extend([size[0]] * (3 - len(size)))
                        elif geo_type in ['capsule', 'cylinder']:
                            # 确保有两个尺寸
                            if len(size) < 2:
                                size.append(1.0)  # 默认高度
                            if len(size) < 3:
                                size.append(0)  # 补充第三个参数
                        
                        # 解析位置（相对于body的局部坐标）
                        local_pos = list(map(float, geom.get('pos', '0 0 0').split())) if 'pos' in geom.attrib else [0, 0, 0]
                        
                        # 解析颜色
                        rgba = geom.get('rgba', '0.8 0.8 0.8 1.0').split()
                        color = list(map(float, rgba))
                        
                        # 创建几何体
                        geo = Geometry(
                            geo_type=geo_type,
                            name=geom_name,
                            position=local_pos,
                            size=size,
                            parent=group
                        )
                        
                        # 设置材质颜色
                        if hasattr(geo, "material"):
                            geo.material.color = color
                        
                        # 添加到组中
                        group.add_child(geo)
                
                # 建立组之间的层级关系
                for body_name, parent_name in parent_map.items():
                    if body_name in body_groups and parent_name in body_groups:
                        child_group = body_groups[body_name]
                        parent_group = body_groups[parent_name]
                        
                        # 避免重复添加
                        if child_group not in parent_group.children:
                            parent_group.add_child(child_group)
                
                # 收集所有顶层组（没有父组的组）
                for name, group in body_groups.items():
                    if name not in parent_map:  # 没有父组
                        geometries.append(group)
                
                # 如果没有找到任何body，处理worldbody下的直接geom
                if not geometries:
                    world_body = root.find(".//worldbody")
                    if world_body is not None:
                        for geom in world_body.findall("geom"):
                            # 排除参考平面和坐标轴
                            geom_name = geom.get('name', '')
                            if geom_name in ["ground", "x_axis", "y_axis", "z_axis"]:
                                continue
                            
                            geo_type = geom.get('type', 'box')
                            pos = list(map(float, geom.get('pos', '0 0 0').split()))
                            size_str = geom.get('size', '1 1 1')
                            size = list(map(float, size_str.split()))
                            
                            # 根据类型调整尺寸格式，同上...
                            
                            # 创建独立几何体
                            geo = Geometry(
                                geo_type=geo_type,
                                name=geom_name or "Object",
                                position=pos,
                                size=size
                            )
                            
                            geometries.append(geo)
            
            else:
                # 其他可能的XML格式，尝试基本解析
                # 直接处理根节点下的geometry元素
                for geom in root.findall(".//geometry"):
                    name = geom.get("name", "Object")
                    geo_type = geom.get("type", "box")
                    
                    # 解析位置
                    pos_elem = geom.find("position")
                    position = [0, 0, 0]
                    if pos_elem is not None:
                        position = [
                            float(pos_elem.get("x", 0)),
                            float(pos_elem.get("y", 0)),
                            float(pos_elem.get("z", 0))
                        ]
                    
                    # 解析尺寸
                    size_elem = geom.find("size")
                    size = [1, 1, 1]
                    if size_elem is not None:
                        size = [
                            float(size_elem.get("x", 1)),
                            float(size_elem.get("y", 1)),
                            float(size_elem.get("z", 1))
                        ]
                    
                    # 解析旋转
                    rot_elem = geom.find("rotation")
                    rotation = [0, 0, 0]
                    if rot_elem is not None:
                        rotation = [
                            float(rot_elem.get("x", 0)),
                            float(rot_elem.get("y", 0)),
                            float(rot_elem.get("z", 0))
                        ]
                    
                    # 创建几何体
                    geo = Geometry(
                        geo_type=geo_type,
                        name=name,
                        position=position,
                        size=size,
                        rotation=rotation
                    )
                    
                    # 处理材质
                    material_elem = geom.find("material")
                    if material_elem is not None:
                        color_attr = material_elem.get("color")
                        if color_attr:
                            color = list(map(float, color_attr.split()))
                            if len(color) >= 3:
                                geo.material.color = color
                    
                    geometries.append(geo)
                
                # 尝试处理group元素
                for group_elem in root.findall(".//group"):
                    name = group_elem.get("name", "Group")
                    
                    # 处理组和子对象...（类似于enhanced_format的处理逻辑）
                    # ...
            
            return geometries
        except Exception as e:
            import traceback
            print(f"文件解析失败: {str(e)}")
            print(traceback.format_exc())
            QMessageBox.critical(None, "错误", f"文件解析失败: {str(e)}")
            return []
    
    @staticmethod
    def save(filename, geometries):
        """
        使用lxml将几何体信息保存为格式化的XML文件
        """
        try:
            from lxml import etree as ET
            
            root = ET.Element("scene")
            
            # 保存几何体信息
            for geo in geometries:
                if hasattr(geo, "children"):  # 检查是否是组
                    continue  # 组会在递归中处理
                
                # 创建几何体元素
                geom = ET.SubElement(root, "geometry")
                geom.set("name", geo.name)
                geom.set("type", geo.type)
                
                # 添加位置信息
                position = ET.SubElement(geom, "position")
                position.set("x", str(geo.position[0]))
                position.set("y", str(geo.position[1]))
                position.set("z", str(geo.position[2]))
                
                # 添加尺寸信息
                size = ET.SubElement(geom, "size")
                size.set("x", str(geo.size[0]))
                size.set("y", str(geo.size[1]))
                size.set("z", str(geo.size[2]))
                
                # 添加旋转信息
                rotation = ET.SubElement(geom, "rotation")
                rotation.set("x", str(geo.rotation[0]))
                rotation.set("y", str(geo.rotation[1]))
                rotation.set("z", str(geo.rotation[2]))
                
                # 添加材质信息
                if hasattr(geo, "material"):
                    material = ET.SubElement(geom, "material")
                    color = geo.material.color
                    if len(color) == 3:
                        material.set("color", f"{color[0]} {color[1]} {color[2]} 1.0")
                    else:
                        material.set("color", f"{color[0]} {color[1]} {color[2]} {color[3]}")
            
            # 递归保存组和子对象
            def save_group(group, parent_elem):
                # 创建组元素
                group_elem = ET.SubElement(parent_elem, "group")
                group_elem.set("name", group.name)
                
                # 添加位置信息
                position = ET.SubElement(group_elem, "position")
                position.set("x", str(group.position[0]))
                position.set("y", str(group.position[1]))
                position.set("z", str(group.position[2]))
                
                # 添加旋转信息
                rotation = ET.SubElement(group_elem, "rotation")
                rotation.set("x", str(group.rotation[0]))
                rotation.set("y", str(group.rotation[1]))
                rotation.set("z", str(group.rotation[2]))
                
                # 保存子对象
                children_elem = ET.SubElement(group_elem, "children")
                for child in group.children:
                    if hasattr(child, "children"):  # 子组
                        save_group(child, children_elem)
                    else:  # 几何体
                        # 创建几何体元素
                        geom = ET.SubElement(children_elem, "geometry")
                        geom.set("name", child.name)
                        geom.set("type", child.type)
                        
                        # 添加位置信息
                        position = ET.SubElement(geom, "position")
                        position.set("x", str(child.position[0]))
                        position.set("y", str(child.position[1]))
                        position.set("z", str(child.position[2]))
                        
                        # 添加尺寸信息
                        size = ET.SubElement(geom, "size")
                        size.set("x", str(child.size[0]))
                        size.set("y", str(child.size[1]))
                        size.set("z", str(child.size[2]))
                        
                        # 添加旋转信息
                        rotation = ET.SubElement(geom, "rotation")
                        rotation.set("x", str(child.rotation[0]))
                        rotation.set("y", str(child.rotation[1]))
                        rotation.set("z", str(child.rotation[2]))
                        
                        # 添加材质信息
                        if hasattr(child, "material"):
                            material = ET.SubElement(geom, "material")
                            color = child.material.color
                            if len(color) == 3:
                                material.set("color", f"{color[0]} {color[1]} {color[2]} 1.0")
                            else:
                                material.set("color", f"{color[0]} {color[1]} {color[2]} {color[3]}")
            
            # 保存所有顶级组
            for obj in geometries:
                if hasattr(obj, "children"):  # 是组
                    save_group(obj, root)
            
            # 创建整洁格式化的XML字符串
            xml_string = ET.tostring(root, encoding='utf-8', pretty_print=True, xml_declaration=True)
            
            # 写入文件
            with open(filename, 'wb') as f:
                f.write(xml_string)
            
            return True
        
        except ImportError:
            # 如果无法导入lxml，给出提示
            print("请安装lxml库以获得更好的XML格式化：pip install lxml")
            
            # 尝试使用标准库（不会有很好的格式化）
            import xml.etree.ElementTree as ET_STD
            # 使用标准库的实现...
            # ...
            return False
        
        except Exception as e:
            print(f"保存XML过程中发生错误：{str(e)}")
            return False
    
    @staticmethod
    def export_enhanced_xml(filename, geometries, include_metadata=False):
        """
        增强版XML导出，支持更多元数据和属性
        
        Args:
            filename: 导出的XML文件路径
            geometries: 要导出的几何体列表或对象树
            include_metadata: 是否包含额外的元数据（创建时间、编辑历史等）
        """
        used_names = set() 
        root = ET.Element("Scene")
        
        # 添加元数据部分
        if include_metadata:
            metadata = ET.SubElement(root, "Metadata")
            from datetime import datetime
            ET.SubElement(metadata, "ExportTime").text = datetime.now().isoformat()
            ET.SubElement(metadata, "Version").text = "2.0"
        
        # 添加几何体对象树
        objects = ET.SubElement(root, "Objects")
        
        # 递归添加几何体和组
        def add_object_to_xml(parent_elem, obj):
            if isinstance(obj, list):
                # 根层级对象列表
                for item in obj:
                    add_object_to_xml(parent_elem, item)
                return
                
            # 为几何体或组创建XML元素
            if hasattr(obj, "type") and obj.type == "group":
                group_name = obj.name
                while group_name in used_names:
                    base_name = group_name.split('_')[0]
                    counter = len([n for n in used_names if n.startswith(base_name)])
                    group_name = f"{base_name}_{counter + 1}"
                used_names.add(group_name)

                elem = ET.SubElement(parent_elem, "Group" ,name=group_name)
                elem.set("name", group_name)
                # 添加位置、旋转等属性
                position = ET.SubElement(elem, "Position")
                position.set("x", str(obj.position[0]))
                position.set("y", str(obj.position[1]))
                position.set("z", str(obj.position[2]))
                
                rotation = ET.SubElement(elem, "Rotation")
                rotation.set("x", str(obj.rotation[0]))
                rotation.set("y", str(obj.rotation[1]))
                rotation.set("z", str(obj.rotation[2]))
                
                # 递归添加子对象
                children = ET.SubElement(elem, "Children")
                for child in obj.children:
                    add_object_to_xml(children, child)
            else:
                geo_name = obj.name
                while geo_name in used_names:
                    base_name = geo_name.split('_')[0]
                    counter = len([n for n in used_names if n.startswith(base_name)])
                    geo_name = f"{base_name}_{counter + 1}"
                used_names.add(geo_name)

                # 几何体对象
                elem = ET.SubElement(parent_elem, "Geometry")
                elem.set("name", geo_name)
                elem.set("type", obj.type)
                
                # 添加详细属性
                position = ET.SubElement(elem, "Position")
                position.set("x", str(obj.position[0]))
                position.set("y", str(obj.position[1]))
                position.set("z", str(obj.position[2]))
                
                size = ET.SubElement(elem, "Size")
                size.set("x", str(obj.size[0]))
                size.set("y", str(obj.size[1]))
                size.set("z", str(obj.size[2]))
                
                rotation = ET.SubElement(elem, "Rotation")
                rotation.set("x", str(obj.rotation[0]))
                rotation.set("y", str(obj.rotation[1]))
                rotation.set("z", str(obj.rotation[2]))
                
                # 添加材质属性
                if hasattr(obj, "material"):
                    material = ET.SubElement(elem, "Material")
                    color = ET.SubElement(material, "Color")
                    color.set("r", str(obj.material.color[0]))
                    color.set("g", str(obj.material.color[1]))
                    color.set("b", str(obj.material.color[2]))
                    color.set("a", str(obj.material.color[3]) if len(obj.material.color) > 3 else "1.0")
        
        # 从根对象开始添加
        add_object_to_xml(objects, geometries)
        
        # 创建树并写入文件
        tree = ET.ElementTree(root)
        
        # 确保XML格式漂亮
        try:
            import xml.dom.minidom as minidom
            xml_str = ET.tostring(root, encoding='utf-8')
            reparsed = minidom.parseString(xml_str)
            pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8')
            
            with open(filename, "wb") as f:
                f.write(pretty_xml)
        except:
            # 如果美化失败，使用标准方法
            tree.write(filename, encoding='utf-8', xml_declaration=True)
        
        return True
    
    @staticmethod
    def import_enhanced_xml(filename):
        """
        导入增强版XML文件
        
        Args:
            filename: XML文件路径
            
        Returns:
            导入的几何体对象列表
        """
        geometries = []
        
        try:
            tree = ET.parse(filename)
            root = tree.getroot()
            
            if root.tag != "Scene":
                raise ValueError("不是有效的场景XML文件")
            
            # 查找对象节点
            objects_node = root.find("Objects")
            if objects_node is None:
                return geometries
            
            # 递归解析对象
            def parse_object(elem, parent=None):
                if elem.tag == "Group":
                    name = elem.get("name", "Group")
                    
                    # 解析位置和旋转
                    position = [0, 0, 0]
                    rotation = [0, 0, 0]
                    
                    pos_elem = elem.find("Position")
                    if pos_elem is not None:
                        position = [
                            float(pos_elem.get("x", "0")),
                            float(pos_elem.get("y", "0")),
                            float(pos_elem.get("z", "0"))
                        ]
                    
                    rot_elem = elem.find("Rotation")
                    if rot_elem is not None:
                        rotation = [
                            float(rot_elem.get("x", "0")),
                            float(rot_elem.get("y", "0")),
                            float(rot_elem.get("z", "0"))
                        ]
                    
                    # 创建组对象
                    group = GeometryGroup(name=name, position=position, rotation=rotation, parent=parent)
                    
                    # 处理子对象
                    children_elem = elem.find("Children")
                    if children_elem is not None:
                        for child_elem in children_elem:
                            child_obj = parse_object(child_elem, group)
                            if child_obj:
                                group.add_child(child_obj)
                    
                    return group
                
                elif elem.tag == "Geometry":
                    name = elem.get("name", "Object")
                    geo_type = elem.get("type", "box")
                    
                    # 解析位置、尺寸和旋转
                    position = [0, 0, 0]
                    size = [1, 1, 1]
                    rotation = [0, 0, 0]
                    
                    pos_elem = elem.find("Position")
                    if pos_elem is not None:
                        position = [
                            float(pos_elem.get("x", "0")),
                            float(pos_elem.get("y", "0")),
                            float(pos_elem.get("z", "0"))
                        ]
                    
                    size_elem = elem.find("Size")
                    if size_elem is not None:
                        size = [
                            float(size_elem.get("x", "1")),
                            float(size_elem.get("y", "1")),
                            float(size_elem.get("z", "1"))
                        ]
                    
                    rot_elem = elem.find("Rotation")
                    if rot_elem is not None:
                        rotation = [
                            float(rot_elem.get("x", "0")),
                            float(rot_elem.get("y", "0")),
                            float(rot_elem.get("z", "0"))
                        ]
                    
                    # 创建几何体对象
                    geo = Geometry(geo_type, name=name, position=position, size=size, rotation=rotation, parent=parent)
                    
                    # 处理材质
                    material_elem = elem.find("Material")
                    if material_elem is not None:
                        color_elem = material_elem.find("Color")
                        if color_elem is not None:
                            color = [
                                float(color_elem.get("r", "1.0")),
                                float(color_elem.get("g", "1.0")),
                                float(color_elem.get("b", "1.0")),
                                float(color_elem.get("a", "1.0"))
                            ]
                            geo.material.color = color
                    
                    return geo
                
                return None
            
            # 处理根层级的对象
            for child in objects_node:
                obj = parse_object(child)
                if obj:
                    geometries.append(obj)
            
        except Exception as e:
            print(f"导入XML文件错误: {e}")
        
        return geometries

    @staticmethod
    def export_mujoco_xml(filename, geometries, include_metadata=False):
        """
        使用lxml库导出为Mujoco格式的XML文件，确保标准格式化缩进
        添加坐标轴和基准平面用于参考
        
        Args:
            filename: 导出的XML文件路径
            geometries: 要导出的几何体列表或对象树
            include_metadata: 参数已不再使用，为了向后兼容保留
        """
        try:
            from lxml import etree as ET
            
            # 创建Mujoco根元素
            root = ET.Element("mujoco", model="scene_export")
            
            # 添加编译器设置
            compiler = ET.SubElement(root, "compiler")
            compiler.set("angle", "degree")
            compiler.set("coordinate", "local")
            compiler.set("eulerseq", "xyz")
            
            # 添加选项
            option = ET.SubElement(root, "option")
            flag = ET.SubElement(option, "flag")
            flag.set("contact", "disable")
            flag.set("gravity", "disable")
            
            # 添加资产
            asset = ET.SubElement(root, "asset")
            
            # 添加网格纹理
            grid_texture = ET.SubElement(asset, "texture")
            grid_texture.set("name", "grid")
            grid_texture.set("type", "2d")
            grid_texture.set("builtin", "checker")
            grid_texture.set("rgb1", ".8 .8 .8")
            grid_texture.set("rgb2", ".9 .9 .9")
            grid_texture.set("width", "300")
            grid_texture.set("height", "300")
            
            # 添加网格材质
            grid_material = ET.SubElement(asset, "material")
            grid_material.set("name", "grid")
            grid_material.set("texture", "grid")
            grid_material.set("texrepeat", "8 8")
            
            # 添加默认材质
            material = ET.SubElement(asset, "material")
            material.set("name", "default")
            material.set("rgba", ".8 .8 .8 1")
            
            # 添加世界信息
            worldbody = ET.SubElement(root, "worldbody")
            
            # 添加光源
            light = ET.SubElement(worldbody, "light")
            light.set("name", "top")
            light.set("pos", "0 0 2")
            light.set("dir", "0 0 -1")
            
            # 添加坐标轴
            # X轴 - 红色
            x_axis = ET.SubElement(worldbody, "geom")
            x_axis.set("name", "x_axis")
            x_axis.set("type", "cylinder")
            x_axis.set("size", "0.02 5")
            x_axis.set("rgba", "1 0 0 1")
            x_axis.set("euler", "0 90 0")
            x_axis.set("pos", "0 0 0")
            
            # Y轴 - 绿色
            y_axis = ET.SubElement(worldbody, "geom")
            y_axis.set("name", "y_axis")
            y_axis.set("type", "cylinder")
            y_axis.set("size", "0.02 5")
            y_axis.set("rgba", "0 1 0 1")
            y_axis.set("euler", "90 0 0")
            y_axis.set("pos", "0 0 0")
            
            # Z轴 - 蓝色
            z_axis = ET.SubElement(worldbody, "geom")
            z_axis.set("name", "z_axis")
            z_axis.set("type", "cylinder")
            z_axis.set("size", "0.02 5")
            z_axis.set("rgba", "0 0 1 1")
            z_axis.set("pos", "0 0 0")
            
            # 添加基准平面
            ground = ET.SubElement(worldbody, "geom")
            ground.set("name", "ground")
            ground.set("type", "plane")
            ground.set("size", "50 50 0.1")
            ground.set("pos", "0 0 0")
            ground.set("material", "grid")
            
            # 递归添加几何体和组
            def add_object_to_mujoco(parent_elem, obj, prefix=""):
                if isinstance(obj, list):
                    # 根层级对象列表
                    for i, item in enumerate(obj):
                        add_object_to_mujoco(parent_elem, item, f"{prefix}{i}_")
                    return
                
                # 创建唯一ID
                safe_name = obj.name.replace(' ', '_').lower()
                obj_id = f"{prefix}{safe_name}"
                
                # 为几何体或组创建XML元素
                if hasattr(obj, "type") and obj.type == "group":
                    # 组被转换为body
                    body = ET.SubElement(parent_elem, "body")
                    body.set("name", obj_id)
                    body.set("pos", f"{obj.position[0]} {obj.position[1]} {obj.position[2]}")
                    
                    # 设置旋转（如果有）
                    if any(obj.rotation):
                        body.set("euler", f"{obj.rotation[0]} {obj.rotation[1]} {obj.rotation[2]}")
                    
                    # 递归添加子对象
                    for i, child in enumerate(obj.children):
                        add_object_to_mujoco(body, child, f"{obj_id}_")
                else:
                    # 几何体对象
                    geom_type_mapping = {
                        GeometryType.BOX: "box",
                        GeometryType.SPHERE: "sphere",
                        GeometryType.CYLINDER: "cylinder",
                        GeometryType.CAPSULE: "capsule",
                        GeometryType.PLANE: "plane",
                        GeometryType.ELLIPSOID: "ellipsoid"
                    }
                    
                    mujoco_type = geom_type_mapping.get(obj.type, "box")
                    
                    # 创建body和geom
                    body = ET.SubElement(parent_elem, "body")
                    body.set("name", obj_id)
                    body.set("pos", f"{obj.position[0]} {obj.position[1]} {obj.position[2]}")
                    
                    # 设置旋转（如果有）
                    if any(obj.rotation):
                        body.set("euler", f"{obj.rotation[0]} {obj.rotation[1]} {obj.rotation[2]}")
                    
                    geom = ET.SubElement(body, "geom")
                    geom.set("name", f"{obj_id}_geom")
                    geom.set("type", mujoco_type)
                    
                    # 设置尺寸（根据几何体类型调整）
                    if mujoco_type == "box":
                        # box使用半尺寸
                        half_size = [s/2 for s in obj.size]
                        geom.set("size", f"{half_size[0]} {half_size[1]} {half_size[2]}")
                    elif mujoco_type == "sphere":
                        # 球体使用半径
                        geom.set("size", f"{obj.size[0]}")
                    elif mujoco_type in ["cylinder", "capsule"]:
                        # 圆柱和胶囊使用半径和高度
                        geom.set("size", f"{obj.size[0]} {obj.size[1]}")
                    else:
                        # 其他类型默认使用原始尺寸
                        geom.set("size", f"{obj.size[0]} {obj.size[1]} {obj.size[2]}")
                    
                    # 设置颜色
                    if hasattr(obj, "material") and hasattr(obj.material, "color"):
                        color = obj.material.color
                        if len(color) == 3:
                            rgba = f"{color[0]} {color[1]} {color[2]} 1"
                        else:
                            rgba = f"{color[0]} {color[1]} {color[2]} {color[3]}"
                        geom.set("rgba", rgba)
            
            # 从根对象开始添加
            add_object_to_mujoco(worldbody, geometries)
            
            # 创建整洁格式化的XML字符串
            xml_string = ET.tostring(root, encoding='utf-8', pretty_print=True, xml_declaration=True)
            
            # 写入文件
            with open(filename, 'wb') as f:
                f.write(xml_string)
            
            return True
        
        except ImportError:
            # 如果无法导入lxml，提示用户安装
            print("请安装lxml库以支持XML导出功能：pip install lxml")
            return False
        except Exception as e:
            print(f"导出过程中发生错误：{str(e)}")
            return False

    @staticmethod
    def _euler_to_quat(euler_angles):
        """
        将欧拉角转换为四元数（适用于Mujoco）
        欧拉角按XYZ顺序，单位为度
        返回格式为"w x y z"的字符串
        """
        try:
            import numpy as np
            from scipy.spatial.transform import Rotation
            
            # 将角度转换为弧度
            angles = np.radians(euler_angles)
            
            # 创建旋转对象并转换为四元数
            r = Rotation.from_euler('xyz', angles)
            quat = r.as_quat()  # 返回[x, y, z, w]格式
            
            # Mujoco使用w, x, y, z顺序
            return f"{quat[3]} {quat[0]} {quat[1]} {quat[2]}"
        except ImportError:
            # 如果没有scipy库，使用简化计算（仅适用于小角度）
            print("警告：未找到scipy库，使用简化四元数计算。请安装scipy以获得准确结果。")
            # 简化计算，仅用于回退
            rad = np.radians(euler_angles)
            cy = np.cos(rad[2] * 0.5)
            sy = np.sin(rad[2] * 0.5)
            cp = np.cos(rad[1] * 0.5)
            sp = np.sin(rad[1] * 0.5)
            cr = np.cos(rad[0] * 0.5)
            sr = np.sin(rad[0] * 0.5)
            
            w = cr * cp * cy + sr * sp * sy
            x = sr * cp * cy - cr * sp * sy
            y = cr * sp * cy + sr * cp * sy
            z = cr * cp * sy - sr * sp * cy
            
            return f"{w} {x} {y} {z}"
