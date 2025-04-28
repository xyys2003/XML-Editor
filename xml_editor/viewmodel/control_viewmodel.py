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
    undoStateChanged = pyqtSignal(bool)  # 撤销状态变化，参数表示是否可以撤销
    redoStateChanged = pyqtSignal(bool)  # 重做状态变化，参数表示是否可以重做
    
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
        
        # 初始化撤销/重做相关的属性
        self._history_files = []  # 历史状态文件列表
        self._current_history_index = -1  # 当前历史状态索引
        self._undo_redo_dir = os.path.join(self._save_dir, "history")
        os.makedirs(self._undo_redo_dir, exist_ok=True)
        
        # 防止过于频繁的保存，增加节流逻辑
        self._last_save_time = datetime.datetime.now()
        self._save_pending = False
        self._save_throttle_ms = 500  # 节流时间（毫秒）
        
        # 连接所有可能导致几何体变化的信号（排除选择变化）
        # 1. 场景视图模型的几何体变化信号
        if hasattr(self._scene_viewmodel, 'geometryChanged'):
            self._scene_viewmodel.geometryChanged.connect(self._on_geometry_modified)
        if hasattr(self._scene_viewmodel, 'geometryAdded'):
            self._scene_viewmodel.geometryAdded.connect(self._on_geometry_modified)
        if hasattr(self._scene_viewmodel, 'geometryDeleted'):
            self._scene_viewmodel.geometryDeleted.connect(self._on_geometry_modified)
        if hasattr(self._scene_viewmodel, 'geometriesChanged'):
            self._scene_viewmodel.geometriesChanged.connect(self._on_geometry_modified)
        if hasattr(self._scene_viewmodel, 'geometriesLoaded'):
            self._scene_viewmodel.geometriesLoaded.connect(self._on_geometry_modified)
        
        # 2. 属性视图模型的属性变化信号(通过场景视图模型连接)
        if hasattr(self._scene_viewmodel, 'propertyViewModel'):
            if hasattr(self._scene_viewmodel.propertyViewModel, 'propertyChanged'):
                self._scene_viewmodel.propertyViewModel.propertyChanged.connect(self._on_geometry_modified)
        
        # 3. 特别针对位置、旋转和缩放属性的变化
        if hasattr(self._scene_viewmodel, 'positionChanged'):
            self._scene_viewmodel.positionChanged.connect(self._on_geometry_modified)
        if hasattr(self._scene_viewmodel, 'rotationChanged'):
            self._scene_viewmodel.rotationChanged.connect(self._on_geometry_modified)
        if hasattr(self._scene_viewmodel, 'scaleChanged'):
            self._scene_viewmodel.scaleChanged.connect(self._on_geometry_modified)
        
        # 4. 连接场景视图模型的对象变化通知（但不包括选择变化）
        if hasattr(self._scene_viewmodel, 'objectChanged'):
            self._scene_viewmodel.objectChanged.connect(self._on_geometry_modified)
        
        # 记录初始状态
        self._record_operation_state()

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

    def _on_selection_changed(self, selected_object):
        """当选择变化时，不记录操作状态"""
        # 选择变化不应该触发撤销/重做，所以这里不做任何处理
        pass

    def _on_geometry_modified(self, *args):
        """
        几何体被修改、添加或删除时调用的处理函数
        自动触发状态保存
        """
        print("几何体发生变化，准备保存状态...")  # 调试输出
        
        # 如果已经标记为待保存，不再处理
        if self._save_pending:
            return
        
        # 使用节流逻辑防止过于频繁的保存
        current_time = datetime.datetime.now()
        time_diff = (current_time - self._last_save_time).total_seconds() * 1000
        
        if time_diff < self._save_throttle_ms:
            # 如果距离上次保存时间太短，标记为待保存
            if not self._save_pending:
                self._save_pending = True
                # 使用Qt的计时器在节流时间后触发保存
                from PyQt5.QtCore import QTimer
                # 将浮点数转换为整数
                delay = int(self._save_throttle_ms - time_diff)
                QTimer.singleShot(delay, self._delayed_record_state)
        else:
            # 已经过了足够的时间，直接保存
            self._save_pending = False
            self._last_save_time = current_time
            self._record_operation_state()

    def _delayed_record_state(self):
        """延迟记录状态，由节流逻辑调用"""
        if self._save_pending:
            self._save_pending = False
            self._last_save_time = datetime.datetime.now()
            self._record_operation_state()

    def _record_operation_state(self):
        """记录操作状态，用于撤销/重做"""
        try:
            print("正在记录操作状态...")  # 调试输出
            
            # 创建时间戳文件名
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(self._undo_redo_dir, f"history_{timestamp}.json")
            
            # 从场景视图模型获取几何体数据
            geometries = self._scene_viewmodel.get_serializable_geometries()
            
            # 写入JSON文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(geometries, f, indent=4)
            
            # 如果在历史记录中间进行了新操作，需要清除当前状态之后的所有历史
            if self._current_history_index < len(self._history_files) - 1:
                # 删除不再需要的历史文件
                for old_file in self._history_files[self._current_history_index + 1:]:
                    if os.path.exists(old_file):
                        try:
                            os.remove(old_file)
                        except:
                            print(f"无法删除文件: {old_file}")
                # 截断历史记录列表
                self._history_files = self._history_files[:self._current_history_index + 1]
            
            # 添加新的历史记录
            self._history_files.append(file_path)
            self._current_history_index = len(self._history_files) - 1
            
            # 更新撤销/重做状态
            self.undoStateChanged.emit(self._current_history_index > 0)
            self.redoStateChanged.emit(False)  # 新操作后不可重做
            
            print(f"操作状态已记录，当前历史记录数: {len(self._history_files)}, 索引: {self._current_history_index}")  # 调试输出
            return file_path
        except Exception as e:
            print(f"记录操作状态失败: {str(e)}")
            return None
    
    @pyqtSlot()
    def undo(self):
        """撤销操作"""
        if self._current_history_index > 0:
            print(f"执行撤销，从 {self._current_history_index} 到 {self._current_history_index - 1}")
            self._current_history_index -= 1
            file_path = self._history_files[self._current_history_index]
            
            try:
                # 确保文件存在
                if not os.path.exists(file_path):
                    print(f"文件不存在: {file_path}")
                    return False
                
                # 读取JSON文件
                with open(file_path, 'r', encoding='utf-8') as f:
                    geometries = json.load(f)
                
                # 暂时禁用状态记录，防止加载过程中触发新的记录
                original_pending = self._save_pending
                self._save_pending = True
                
                # 将几何体数据传递给场景视图模型
                success = self._scene_viewmodel.load_geometries_from_data(geometries)
                
                # 恢复状态记录设置
                self._save_pending = original_pending
                
                # 发送状态变化信号
                self.undoStateChanged.emit(self._current_history_index > 0)
                self.redoStateChanged.emit(self._current_history_index < len(self._history_files) - 1)
                
                print(f"撤销{'成功' if success else '失败'}")
                return success
            except Exception as e:
                print(f"撤销操作失败: {str(e)}")
                return False
        
        print("无法撤销，没有更早的历史记录")
        return False
    
    @pyqtSlot()
    def redo(self):
        """重做操作"""
        if self._current_history_index < len(self._history_files) - 1:
            print(f"执行重做，从 {self._current_history_index} 到 {self._current_history_index + 1}")
            self._current_history_index += 1
            file_path = self._history_files[self._current_history_index]
            
            try:
                # 确保文件存在
                if not os.path.exists(file_path):
                    print(f"文件不存在: {file_path}")
                    return False
                
                # 读取JSON文件
                with open(file_path, 'r', encoding='utf-8') as f:
                    geometries = json.load(f)
                
                # 暂时禁用状态记录，防止加载过程中触发新的记录
                original_pending = self._save_pending
                self._save_pending = True
                
                # 将几何体数据传递给场景视图模型
                success = self._scene_viewmodel.load_geometries_from_data(geometries)
                
                # 恢复状态记录设置
                self._save_pending = original_pending
                
                # 发送状态变化信号
                self.undoStateChanged.emit(self._current_history_index > 0)
                self.redoStateChanged.emit(self._current_history_index < len(self._history_files) - 1)
                
                print(f"重做{'成功' if success else '失败'}")
                return success
            except Exception as e:
                print(f"重做操作失败: {str(e)}")
                return False
        
        print("无法重做，没有更新的历史记录")
        return False
    
    def clear_history(self):
        """清除所有历史记录"""
        try:
            # 删除所有历史文件
            for file_path in self._history_files:
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            # 重置历史记录
            self._history_files = []
            self._current_history_index = -1
            
            # 记录当前状态作为新的初始状态
            self._record_operation_state()
            
            # 更新撤销/重做状态
            self.undoStateChanged.emit(False)
            self.redoStateChanged.emit(False)
            
            return True
        except Exception as e:
            print(f"清除历史记录失败: {str(e)}")
            return False
    
    def can_undo(self):
        """检查是否可以撤销"""
        return self._current_history_index > 0
    
    def can_redo(self):
        """检查是否可以重做"""
        return self._current_history_index < len(self._history_files) - 1
