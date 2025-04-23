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
        
        # 首先处理世界body（没有父节点的body）
        world_body = root.find(".//worldbody")
        if world_body is not None:
            world_group = GeometryGroup(name="World")
            
            # 处理直接在worldbody下的geom
            for geom in world_body.findall("./geom"):
                geo = XMLParser._process_mujoco_geom(geom, parent=world_group)
                if geo:
                    world_group.add_child(geo)
            
            # 处理worldbody下的body
            for body in world_body.findall("./body"):
                body_group = XMLParser._process_mujoco_body(body, parent=world_group)
                if body_group:
                    world_group.add_child(body_group)
                    body_name = body.get('name', 'Unnamed')
                    body_groups[body_name] = body_group
            
            geometries.append(world_group)
        
        # 更新所有几何体的变换矩阵
        XMLParser._update_transforms_recursive(geometries)
        
        return geometries
    
    @staticmethod
    def _process_mujoco_geom(geom_elem, parent=None):
        """处理MuJoCo XML中的geom元素"""
        geom_name = geom_elem.get('name', 'Geom')
        geom_type = geom_elem.get('type', 'box')
        
        # 位置 (x,y,z)
        pos_str = geom_elem.get('pos', '0 0 0')
        pos = [float(x) for x in pos_str.split()]
        if len(pos) < 3:
            pos.extend([0] * (3 - len(pos)))
        
        # 尺寸 (在MuJoCo中，大小表示方式与几何体类型有关)
        size_str = geom_elem.get('size', '0.1 0.1 0.1')
        size = [float(x) for x in size_str.split()]
        if len(size) < 3:
            if geom_type == 'sphere':
                # 球体：半径
                size = [size[0], size[0], size[0]]
            elif geom_type == 'cylinder' or geom_type == 'capsule':
                # 圆柱/胶囊：半径和半高
                size = [size[0], size[0], size[1] if len(size) > 1 else size[0]]
            else:
                # 默认补全为立方体
                size.extend([0.1] * (3 - len(size)))
        
        # 旋转 (MuJoCo使用四元数或欧拉角)
        euler = [0, 0, 0]
        quat_str = geom_elem.get('quat', None)
        if quat_str:
            quat = [float(x) for x in quat_str.split()]
            if len(quat) == 4:
                # 将四元数转换为欧拉角，这里简化实现
                euler = XMLParser._quat_to_euler(quat)
        else:
            # 也可能使用欧拉角赋值
            euler_str = geom_elem.get('euler', '0 0 0')
            euler = [float(x) for x in euler_str.split()]
            if len(euler) < 3:
                euler.extend([0] * (3 - len(euler)))
        
        # 创建几何体
        geo = Geometry(
            geo_type=geom_type,
            name=geom_name,
            position=pos,
            size=size,
            rotation=euler,
            parent=parent
        )
        
        # 处理颜色属性
        rgba_str = geom_elem.get('rgba', None)
        if rgba_str:
            rgba = [float(x) for x in rgba_str.split()]
            if len(rgba) == 4:
                geo.material.color = rgba
        
        return geo
    
    @staticmethod
    def _process_mujoco_body(body_elem, parent=None):
        """处理MuJoCo XML中的body元素"""
        body_name = body_elem.get('name', 'Body')
        
        # 位置
        pos_str = body_elem.get('pos', '0 0 0')
        pos = [float(x) for x in pos_str.split()]
        if len(pos) < 3:
            pos.extend([0] * (3 - len(pos)))
        
        # 旋转
        euler = [0, 0, 0]
        quat_str = body_elem.get('quat', None)
        if quat_str:
            quat = [float(x) for x in quat_str.split()]
            if len(quat) == 4:
                euler = XMLParser._quat_to_euler(quat)
        else:
            euler_str = body_elem.get('euler', '0 0 0')
            euler = [float(x) for x in euler_str.split()]
            if len(euler) < 3:
                euler.extend([0] * (3 - len(euler)))
        
        # 创建组
        group = GeometryGroup(
            name=body_name,
            position=pos,
            rotation=euler,
            parent=parent
        )
        
        # 处理body中的所有geom
        for geom in body_elem.findall("./geom"):
            geo = XMLParser._process_mujoco_geom(geom, parent=group)
            if geo:
                group.add_child(geo)
        
        # 处理嵌套body
        for child_body in body_elem.findall("./body"):
            child_group = XMLParser._process_mujoco_body(child_body, parent=group)
            if child_group:
                group.add_child(child_group)
        
        return group
    
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
    def export_enhanced_xml(filename, geometries):
        """
        导出场景为增强XML格式（自定义格式）
        
        参数:
            filename: 保存文件路径
            geometries: 几何体对象列表
            
        返回:
            bool: 是否成功导出
        """
        try:
            root = ET.Element("Scene")
            objects_elem = ET.SubElement(root, "Objects")
            
            # 递归添加对象
            for obj in geometries:
                XMLParser._add_object_to_enhanced_xml(objects_elem, obj)
            
            # 创建XML树
            tree = ET.ElementTree(root)
            
            # 写入文件
            tree.write(filename, encoding="utf-8", xml_declaration=True)
            return True
        except Exception as e:
            print(f"导出增强XML时出错: {e}")
            return False
    
    @staticmethod
    def _add_object_to_enhanced_xml(parent_elem, obj):
        """递归添加对象到增强XML"""
        if obj.type == "group":
            # 处理组
            group_elem = ET.SubElement(parent_elem, "Group")
            group_elem.set("name", obj.name)
            
            # 添加位置
            pos_elem = ET.SubElement(group_elem, "Position")
            pos_elem.set("x", str(obj.position[0]))
            pos_elem.set("y", str(obj.position[1]))
            pos_elem.set("z", str(obj.position[2]))
            
            # 添加旋转
            rot_elem = ET.SubElement(group_elem, "Rotation")
            rot_elem.set("x", str(obj.rotation[0]))
            rot_elem.set("y", str(obj.rotation[1]))
            rot_elem.set("z", str(obj.rotation[2]))
            
            # 处理子对象
            if obj.children:
                children_elem = ET.SubElement(group_elem, "Children")
                for child in obj.children:
                    XMLParser._add_object_to_enhanced_xml(children_elem, child)
        else:
            # 处理几何体
            geo_elem = ET.SubElement(parent_elem, "Geometry")
            geo_elem.set("name", obj.name)
            geo_elem.set("type", obj.type)
            
            # 添加位置
            pos_elem = ET.SubElement(geo_elem, "Position")
            pos_elem.set("x", str(obj.position[0]))
            pos_elem.set("y", str(obj.position[1]))
            pos_elem.set("z", str(obj.position[2]))
            
            # 添加尺寸
            size_elem = ET.SubElement(geo_elem, "Size")
            size_elem.set("x", str(obj.size[0]))
            size_elem.set("y", str(obj.size[1]))
            size_elem.set("z", str(obj.size[2]))
            
            # 添加旋转
            rot_elem = ET.SubElement(geo_elem, "Rotation")
            rot_elem.set("x", str(obj.rotation[0]))
            rot_elem.set("y", str(obj.rotation[1]))
            rot_elem.set("z", str(obj.rotation[2]))
            
            # 添加材质
            material_elem = ET.SubElement(geo_elem, "Material")
            color_elem = ET.SubElement(material_elem, "Color")
            color_elem.set("r", str(obj.material.color[0]))
            color_elem.set("g", str(obj.material.color[1]))
            color_elem.set("b", str(obj.material.color[2]))
            color_elem.set("a", str(obj.material.color[3]))
    
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
            
            # 创建XML树
            tree = ET.ElementTree(root)
            
            # 写入文件
            tree.write(filename, encoding="utf-8", xml_declaration=True)
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
                # 圆柱/胶囊：使用第一个尺寸作为半径，第三个作为半高
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
    
    
    # 保存方法别名，使用增强XML格式
    save = export_enhanced_xml 
