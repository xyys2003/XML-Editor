"""
XML解析器

处理MJCF文件的加载、解析和保存功能。
"""

import xml.etree.ElementTree as ET
import numpy as np
from .geometry import Geometry, GeometryGroup, GeometryType

class XMLParser:
    """
    XML文件解析和生成工具
    
    用于处理MJCF场景的加载和保存，支持两种格式：
    1. 增强XML格式（自定义格式，更适合编辑器内部使用）
    2. MuJoCo XML格式（标准MJCF格式）
    """
    
    @staticmethod
    def load(filename):
        """
        从XML文件导入几何体和组层级结构
        
        参数:
            filename: 要加载的XML文件路径
            
        返回:
            几何体对象列表
        """
        try:
            tree = ET.parse(filename)
            root = tree.getroot()
            
            # 检查文件格式类型
            is_mujoco_format = root.tag == "mujoco"
            is_enhanced_format = root.tag == "Scene"
            
            if is_enhanced_format:
                return XMLParser._load_enhanced_format(root)
            elif is_mujoco_format:
                return XMLParser._load_mujoco_format(root)
            else:
                raise ValueError(f"不支持的XML格式：{root.tag}")
        except Exception as e:
            print(f"加载XML文件时出错: {e}")
            return []
    
    @staticmethod
    def _load_enhanced_format(root):
        """
        处理增强XML格式（自定义格式）
        
        参数:
            root: XML根元素
            
        返回:
            几何体对象列表
        """
        geometries = []
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
                        
                        # 确保变换矩阵被更新
                        if hasattr(group, "update_transform_matrix"):
                            group.update_transform_matrix()
                        
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
                        
                        # 确保变换矩阵被更新
                        if hasattr(geo, "update_transform_matrix"):
                            geo.update_transform_matrix()
                        
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
        
        return geometries
    
    @staticmethod
    def _load_mujoco_format(root):
        """
        处理MuJoCo XML格式
        
        参数:
            root: XML根元素
            
        返回:
            几何体对象列表
        """
        geometries = []
        
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
            
            # 检查四元数表示
            if 'quat' in body.attrib:
                quat = list(map(float, body.get('quat').split()))
                if len(quat) == 4:
                    body_euler = XMLParser._quat_to_euler(quat)
            
            # 创建组对象
            group = GeometryGroup(
                name=body_name,
                position=body_pos,
                rotation=body_euler
            )
            
            # 确保变换矩阵被更新
            if hasattr(group, "update_transform_matrix"):
                group.update_transform_matrix()
            
            body_groups[body_name] = group
            
            # 添加所有geom子对象
            for geom in body.findall("geom"):
                geo_type = geom.get('type', 'box')
                geom_name = geom.get('name', f"{body_name}_geom")
                
                # 解析尺寸
                size_str = geom.get('size', '1 1 1')
                size = list(map(float, size_str.split()))
                
                # 适当地处理尺寸格式
                if geo_type == 'sphere':
                    if len(size) == 1:
                        size = [size[0], size[0], size[0]]  # 保持三个相同的半径值
                elif geo_type == 'ellipsoid':
                    # 确保有三个尺寸
                    if len(size) < 3:
                        size.extend([size[0]] * (3 - len(size)))
                elif geo_type in ['capsule', 'cylinder']:
                    # 确保有两个尺寸
                    if len(size) < 2:
                        size.append(1.0)  # 默认半高
                    if len(size) < 3:
                        size.append(0)  # 补充第三个参数
                
                # 解析位置（相对于body的局部坐标）
                local_pos = list(map(float, geom.get('pos', '0 0 0').split())) if 'pos' in geom.attrib else [0, 0, 0]
                
                # 解析旋转
                local_euler = [0, 0, 0]
                if 'euler' in geom.attrib:
                    local_euler = list(map(float, geom.get('euler').split()))
                elif 'quat' in geom.attrib:
                    quat = list(map(float, geom.get('quat').split()))
                    if len(quat) == 4:
                        local_euler = XMLParser._quat_to_euler(quat)
                
                # 解析颜色
                color = [0.8, 0.8, 0.8, 1.0]  # 默认灰色
                
                # 优先使用rgba属性
                if 'rgba' in geom.attrib:
                    rgba_str = geom.get('rgba')
                    rgba_values = list(map(float, rgba_str.split()))
                    # 确保有四个值
                    if len(rgba_values) == 3:
                        rgba_values.append(1.0)  # 添加alpha默认值
                    elif len(rgba_values) < 3:
                        rgba_values = [0.8, 0.8, 0.8, 1.0]  # 默认灰色
                    color = rgba_values
                # 检查是否引用了material
                elif 'material' in geom.attrib:
                    material_name = geom.get('material')
                    # 尝试在asset下找到对应的material
                    material_elem = root.find(f".//asset/material[@name='{material_name}']")
                    if material_elem is not None and 'rgba' in material_elem.attrib:
                        rgba_str = material_elem.get('rgba')
                        color = list(map(float, rgba_str.split()))
                        if len(color) == 3:
                            color.append(1.0)  # 添加默认透明度
                
                # 创建几何体
                geo = Geometry(
                    geo_type=geo_type,
                    name=geom_name,
                    position=local_pos,
                    size=size,
                    rotation=local_euler,
                    parent=group
                )
                
                # 设置颜色
                geo.material.color = color
                
                # 确保变换矩阵被更新
                if hasattr(geo, "update_transform_matrix"):
                    geo.update_transform_matrix()
                
                # 添加到组中
                group.add_child(geo)
        
        # 在返回前进行一次全面的变换矩阵更新
        # 先确保所有父子关系已经建立
        for body_name, parent_name in parent_map.items():
            if body_name in body_groups and parent_name in body_groups:
                child_group = body_groups[body_name]
                parent_group = body_groups[parent_name]
                
                # 避免重复添加
                if child_group not in parent_group.children:
                    parent_group.add_child(child_group)
        
        # 收集所有顶层组（没有父组的组）
        top_level_groups = []
        for name, group in body_groups.items():
            if name not in parent_map:  # 没有父组
                top_level_groups.append(group)
        
        # 如果找到了顶层组，将它们添加到geometries
        if top_level_groups:
            geometries.extend(top_level_groups)
        
        # 处理worldbody下的直接geom
        world_body = root.find(".//worldbody")
        if world_body is not None:
            # 创建一个世界组来容纳直接的几何体
            world_group = None
            
            for geom in world_body.findall("geom"):
                # 排除参考平面和坐标轴
                geom_name = geom.get('name', '')
                if geom_name in ["ground", "x_axis", "y_axis", "z_axis"]:
                    continue
                
                # 如果还没有创建世界组并且找到有效几何体，创建一个世界组
                if world_group is None:
                    world_group = GeometryGroup(name="World")
                    geometries.append(world_group)
                
                geo_type = geom.get('type', 'box')
                pos = list(map(float, geom.get('pos', '0 0 0').split()))
                size_str = geom.get('size', '1 1 1')
                size = list(map(float, size_str.split()))
                
                # 根据类型调整尺寸格式
                if geo_type == 'sphere':
                    if len(size) == 1:
                        size = [size[0], size[0], size[0]]
                elif geo_type in ['capsule', 'cylinder']:
                    if len(size) < 2:
                        size.append(1.0)
                    if len(size) < 3:
                        size.append(0)
                elif len(size) < 3:
                    size.extend([1.0] * (3 - len(size)))
                
                # 解析旋转
                euler = [0, 0, 0]
                if 'euler' in geom.attrib:
                    euler = list(map(float, geom.get('euler').split()))
                elif 'quat' in geom.attrib:
                    quat = list(map(float, geom.get('quat').split()))
                    if len(quat) == 4:
                        euler = XMLParser._quat_to_euler(quat)
                
                # 解析颜色
                color = [0.8, 0.8, 0.8, 1.0]  # 默认灰色
                
                if 'rgba' in geom.attrib:
                    rgba_str = geom.get('rgba')
                    rgba_values = list(map(float, rgba_str.split()))
                    if len(rgba_values) >= 3:
                        color = rgba_values
                        if len(color) == 3:
                            color.append(1.0)  # 添加alpha默认值
                
                # 创建几何体
                geo = Geometry(
                    geo_type=geo_type,
                    name=geom_name or "Object",
                    position=pos,
                    size=size,
                    rotation=euler,
                    parent=world_group
                )
                
                # 设置材质
                geo.material.color = color
                
                # 确保变换矩阵被更新
                if hasattr(geo, "update_transform_matrix"):
                    geo.update_transform_matrix()
                
                if world_group is not None:
                    world_group.add_child(geo)
                else:
                    geometries.append(geo)
        
        # 最后，对所有对象进行两遍更新以确保变换正确传播
        # 第一遍：更新所有对象的本地变换
        XMLParser._update_transforms_recursive(geometries)
        
        # 第二遍：确保世界变换正确传播
        XMLParser._update_world_transforms_recursive(geometries)
        
        # 强制更新并通知每个对象已更改
        XMLParser._force_notify_objects_changed(geometries)
        
        return geometries
    
    @staticmethod
    def _update_transforms_recursive(objects):
        """递归更新所有几何体的变换矩阵"""
        if isinstance(objects, list):
            for obj in objects:
                XMLParser._update_transforms_recursive(obj)
        else:
            # 更新当前对象的变换矩阵
            if hasattr(objects, "update_transform_matrix"):
                objects.update_transform_matrix()
            
            # 如果是组，递归更新子对象
            if hasattr(objects, "children") and objects.children:
                for child in objects.children:
                    XMLParser._update_transforms_recursive(child)
    
    @staticmethod
    def _update_world_transforms_recursive(objects):
        """递归更新所有几何体的世界变换矩阵"""
        if isinstance(objects, list):
            for obj in objects:
                XMLParser._update_world_transforms_recursive(obj)
        else:
            # 更新当前对象的全局变换
            if hasattr(objects, "update_global_transform"):
                objects.update_global_transform()
            elif hasattr(objects, "update_transform_matrix"):
                # 如果没有专门的全局变换更新方法，使用常规更新
                objects.update_transform_matrix()
            
            # 如果是组，递归更新子对象
            if hasattr(objects, "children") and objects.children:
                for child in objects.children:
                    XMLParser._update_world_transforms_recursive(child)
    
    @staticmethod
    def export_mujoco_xml(filename, geometries):
        """
        导出场景为MuJoCo XML格式
        
        参数:
            filename: 保存文件路径
            geometries: 几何体对象列表
            
        返回:
            bool: 是否成功导出
        """
        try:
            # 创建MuJoCo XML根节点
            root = ET.Element("mujoco")
            root.set("model", "MJCFScene")
            
            # 添加编译器选项
            compiler = ET.SubElement(root, "compiler")
            compiler.set("angle", "degree")  # 使用角度而不是弧度
            
            # 创建资源部分
            asset = ET.SubElement(root, "asset")
            
            # 创建世界体
            worldbody = ET.SubElement(root, "worldbody")
            
            # 递归添加几何体
            for obj in geometries:
                XMLParser._add_object_to_mujoco(worldbody, obj)
            
            # 创建并格式化XML树
            tree = ET.ElementTree(root)
            
            # 使用minidom格式化XML
            from xml.dom import minidom
            rough_string = ET.tostring(root, 'utf-8')
            reparsed = minidom.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent="  ")
            
            # 写入文件
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(pretty_xml)
            
            return True
        except Exception as e:
            print(f"导出MuJoCo XML时出错: {e}")
            return False
    
    @staticmethod
    def _add_object_to_mujoco(parent_elem, obj, prefix=""):
        """递归添加对象到MuJoCo XML"""
        if obj.type == "group":
            # 处理组 -> body
            body_elem = ET.SubElement(parent_elem, "body")
            body_elem.set("name", f"{prefix}{obj.name}")
            
            # 设置位置
            body_elem.set("pos", f"{obj.position[0]} {obj.position[1]} {obj.position[2]}")
            
            # 设置旋转（使用欧拉角）
            if any(obj.rotation):
                body_elem.set("euler", f"{obj.rotation[0]} {obj.rotation[1]} {obj.rotation[2]}")
            
            # 递归处理子对象
            for child in obj.children:
                XMLParser._add_object_to_mujoco(body_elem, child, prefix=f"{prefix}{obj.name}_")
        else:
            # 处理几何体 -> geom
            geom_elem = ET.SubElement(parent_elem, "geom")
            geom_elem.set("name", f"{prefix}{obj.name}")
            geom_elem.set("type", obj.type)
            
            # 根据几何体类型设置尺寸
            if obj.type == GeometryType.SPHERE.value:
                # 球体：只使用第一个尺寸作为半径
                geom_elem.set("size", f"{obj.size[0]}")
            elif obj.type in [GeometryType.CYLINDER.value, GeometryType.CAPSULE.value]:
                # 圆柱/胶囊：第一个尺寸为半径，第三个尺寸为半高
                geom_elem.set("size", f"{obj.size[0]} {obj.size[2]}")
            else:
                # 其他几何体：使用所有尺寸
                geom_elem.set("size", f"{obj.size[0]} {obj.size[1]} {obj.size[2]}")
            
            # 设置位置
            geom_elem.set("pos", f"{obj.position[0]} {obj.position[1]} {obj.position[2]}")
            
            # 设置旋转（使用欧拉角）
            if any(obj.rotation):
                geom_elem.set("euler", f"{obj.rotation[0]} {obj.rotation[1]} {obj.rotation[2]}")
            
            # 设置颜色
            geom_elem.set("rgba", f"{obj.material.color[0]} {obj.material.color[1]} {obj.material.color[2]} {obj.material.color[3]}")
    
    @staticmethod
    def _quat_to_euler(quat):
        """四元数转欧拉角（ZYX顺序）"""
        # 实现四元数到欧拉角的转换
        # 这里使用简化的计算方法
        w, x, y, z = quat
        
        # 计算姿态角
        t0 = 2.0 * (w * x + y * z)
        t1 = 1.0 - 2.0 * (x * x + y * y)
        roll = np.degrees(np.arctan2(t0, t1))
        
        t2 = 2.0 * (w * y - z * x)
        t2 = np.clip(t2, -1.0, 1.0)
        pitch = np.degrees(np.arcsin(t2))
        
        t3 = 2.0 * (w * z + x * y)
        t4 = 1.0 - 2.0 * (y * y + z * z)
        yaw = np.degrees(np.arctan2(t3, t4))
        
        return [roll, pitch, yaw]
    
    @staticmethod
    def _force_notify_objects_changed(objects):
        """
        强制通知所有对象已更改，触发必要的更新
        
        这是一个静态方法，无法直接访问scene_model，
        因此需要通过对象本身发送通知
        """
        if isinstance(objects, list):
            for obj in objects:
                XMLParser._force_notify_objects_changed(obj)
        else:
            # 尝试触发对象自身的更新通知
            if hasattr(objects, "notify_changed") and callable(objects.notify_changed):
                objects.notify_changed()
            
            # 触发变换矩阵更新
            if hasattr(objects, "update_transform_matrix"):
                objects.update_transform_matrix()
            
            # 手动触发属性更新以模拟set_property的行为
            if hasattr(objects, "position"):
                try:
                    # 保存当前位置
                    original_position = objects.position.copy() if hasattr(objects.position, "copy") else objects.position[:]
                    # 临时设置新值，触发更新
                    objects.position = original_position
                except Exception as e:
                    print(f"更新位置时出错: {e}")
                
            if hasattr(objects, "rotation"):
                try:
                    # 保存当前旋转
                    original_rotation = objects.rotation.copy() if hasattr(objects.rotation, "copy") else objects.rotation[:]
                    # 临时设置新值，触发更新
                    objects.rotation = original_rotation
                except Exception as e:
                    print(f"更新旋转时出错: {e}")
            
            if hasattr(objects, "size"):
                try:
                    # 检查size是否为数组且不为空
                    has_size = False
                    if isinstance(objects.size, np.ndarray):
                        has_size = objects.size.size > 0
                    elif isinstance(objects.size, (list, tuple)):
                        has_size = len(objects.size) > 0
                    else:
                        has_size = bool(objects.size)
                    
                    if has_size:
                        # 保存当前大小
                        original_size = objects.size.copy() if hasattr(objects.size, "copy") else objects.size[:]
                        # 临时设置新值，触发更新
                        objects.size = original_size
                except Exception as e:
                    print(f"更新尺寸时出错: {e}")
            
            # 递归处理子对象
            if hasattr(objects, "children") and objects.children:
                for child in objects.children:
                    XMLParser._force_notify_objects_changed(child)
    
    # 保存方法别名，使用增强XML格式
    save = export_mujoco_xml
