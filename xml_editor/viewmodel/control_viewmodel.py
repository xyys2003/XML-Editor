"""
控制面板视图模型

处理工具选择和操作模式等控制逻辑。
"""

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from ..model.geometry import OperationMode, GeometryType
from ..viewmodel.scene_viewmodel import SceneViewModel
import json
import os
import datetime
import glob

class ControlViewModel(QObject):
    """
    控制面板视图模型类
    
    处理工具选择、操作模式和几何体创建等控制逻辑
    """
    # 信号
    operationModeChanged = pyqtSignal(object)  # 操作模式变化
    coordinateSystemChanged = pyqtSignal(bool)  # 坐标系变化，True表示局部坐标系，False表示全局坐标系
    saveStateCompleted = pyqtSignal(str)  # 保存状态完成，参数为保存路径
    loadStateCompleted = pyqtSignal(bool)  # 加载状态完成，参数表示是否成功
    
    def __init__(self, scene_viewmodel:SceneViewModel):
        """
        初始化控制面板视图模型
        
        参数:
            scene_viewmodel: 场景视图模型的引用
        """
        super().__init__()
        self._scene_viewmodel = scene_viewmodel
        
        # 连接场景视图模型的信号
        self._scene_viewmodel.operationModeChanged.connect(self.operationModeChanged)
        
        # 添加对坐标系变化的处理
        if hasattr(self._scene_viewmodel, 'coordinateSystemChanged'):
            self._scene_viewmodel.coordinateSystemChanged.connect(self.coordinateSystemChanged)
        
        # 确保存档目录存在
        self._save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "save")
        os.makedirs(self._save_dir, exist_ok=True)

    @property
    def operation_mode(self):
        """获取当前操作模式"""
        return self._scene_viewmodel.operation_mode
    
    @operation_mode.setter
    def operation_mode(self, value):
        """设置操作模式"""
        self._scene_viewmodel.operation_mode = value
        self.operationModeChanged.emit(value)
    
    @property
    def use_local_coords(self):
        """获取当前坐标系模式，True表示局部坐标系，False表示全局坐标系"""
        return self._scene_viewmodel.use_local_coords if hasattr(self._scene_viewmodel, 'use_local_coords') else True
    
    @use_local_coords.setter
    def use_local_coords(self, value):
        """设置坐标系模式"""
        if hasattr(self._scene_viewmodel, 'use_local_coords'):
            self._scene_viewmodel.use_local_coords = value
            self.coordinateSystemChanged.emit(value)

    @pyqtSlot(str)
    def save_state_to_json(self, file_path):
        """
        将当前几何体状态保存到JSON文件
        
        参数:
            file_path: 保存文件的路径
        """
        try:
            # 从场景视图模型获取几何体数据
            geometries = self._scene_viewmodel.get_serializable_geometries()
            
            # 确保文件路径有.json扩展名
            if not file_path.lower().endswith('.json'):
                file_path += '.json'
            
            # 写入JSON文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(geometries, f, indent=4)
            
            # 发送保存完成信号
            self.saveStateCompleted.emit(file_path)
            return True
        except Exception as e:
            print(f"保存几何体数据失败: {str(e)}")
            return False
    
    @pyqtSlot(str)
    def load_state_from_json(self, file_path):
        """
        从JSON文件加载几何体状态
        
        参数:
            file_path: JSON文件路径
        """
        try:
            # 确保文件存在
            if not os.path.exists(file_path):
                self.loadStateCompleted.emit(False)
                return False
            
            # 读取JSON文件
            with open(file_path, 'r', encoding='utf-8') as f:
                geometries = json.load(f)
            
            # 将几何体数据传递给场景视图模型
            success = self._scene_viewmodel.load_geometries_from_data(geometries)
            
            # 发送加载完成信号
            self.loadStateCompleted.emit(success)
            return success
        except Exception as e:
            print(f"加载几何体数据失败: {str(e)}")
            self.loadStateCompleted.emit(False)
            return False

    @pyqtSlot()
    def auto_save_state(self):
        """
        自动保存当前几何体状态到时间戳命名的文件
        
        返回:
            str: 保存的文件路径，如果保存失败则返回None
        """
        try:
            # 创建时间戳文件名
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(self._save_dir, f"{timestamp}.json")
            
            # 从场景视图模型获取几何体数据
            geometries = self._scene_viewmodel.get_serializable_geometries()
            
            # 写入JSON文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(geometries, f, indent=4)
            
            # 发送保存完成信号
            self.saveStateCompleted.emit(file_path)
            return file_path
        except Exception as e:
            print(f"自动保存几何体数据失败: {str(e)}")
            return None
    
    def get_recent_saves(self, count=10):
        """
        获取最近的存档文件列表
        
        参数:
            count: 要返回的存档数量
            
        返回:
            list: 存档文件路径列表，按时间倒序排序
        """
        try:
            # 获取所有JSON文件
            json_files = glob.glob(os.path.join(self._save_dir, "*.json"))
            
            # 按修改时间排序
            json_files.sort(key=os.path.getmtime, reverse=True)
            
            # 返回指定数量的文件
            return json_files[:count]
        except Exception as e:
            print(f"获取最近存档失败: {str(e)}")
            return []
    
    def get_save_info(self, file_path):
        """
        获取存档文件的简要信息
        
        参数:
            file_path: 存档文件路径
            
        返回:
            dict: 包含存档信息的字典
        """
        try:
            # 获取文件修改时间
            mtime = os.path.getmtime(file_path)
            mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            
            # 提取文件名(不含路径和扩展名)
            filename = os.path.basename(file_path)
            name_without_ext = os.path.splitext(filename)[0]
            
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 获取几何体数量
            geo_count = len(data.get('geometries', []))
            
            return {
                'path': file_path,
                'name': name_without_ext,
                'time': mtime_str,
                'geometry_count': geo_count
            }
        except Exception as e:
            print(f"获取存档信息失败: {str(e)}")
            return {
                'path': file_path,
                'name': os.path.basename(file_path),
                'time': '未知',
                'geometry_count': 0
            }

    def print_save_content(self, file_path):
        """
        打印存档文件内容，用于调试
        
        参数:
            file_path: 存档文件路径
        """
        try:
            if not os.path.exists(file_path):
                print(f"文件不存在: {file_path}")
                return
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"存档版本: {data.get('version', '未知')}")
            print(f"几何体数量: {len(data.get('geometries', []))}")
            
            # 打印每个几何体的基本信息
            for i, geo in enumerate(data.get('geometries', [])):
                print(f"几何体 {i+1}:")
                print(f"  类型: {geo.get('type')}")
                print(f"  名称: {geo.get('name')}")
                print(f"  位置: {geo.get('position')}")
                print(f"  尺寸: {geo.get('scale')}")
                print(f"  旋转: {geo.get('rotation')}")
                print(f"  颜色: {geo.get('color')}")
                print("")
            
            return data
        except Exception as e:
            print(f"读取存档文件失败: {str(e)}")
            return None
