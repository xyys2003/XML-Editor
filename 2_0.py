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


# ========== 3D视图组件 ==========
class OpenGLWidget(QOpenGLWidget):
    selection_changed = pyqtSignal(object)
    transform_mode_changed = pyqtSignal(int)
    geometriesChanged = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.geometries = []
        self.selected_geo = None
        self.transform_mode = TransformMode.TRANSLATE
        self.current_mode = OperationMode.MODE_OBSERVE
        self.use_orthographic = False
        
        # 保留球坐标系参数作为内部计算用
        self._camera_theta = 45.0
        self._camera_phi = 45.0
        self._camera_radius = 15.0
        self. _camera_target = np.array([0.0, 0.0, 0.0])
        
        # 相机初始设置（用于重置）
        self._camera_initial = {
            'theta': 45.0,
            'phi': 45.0,
            'radius': 15.0,
            'target': np.array([0.0, 0.0, 0.0])
        }
        
        # 将世界上方向设置为Z轴
        self.world_up = np.array([0.0, 0.0, 1.0])
        
        # 统一的相机配置（包含position,view,projection,viewport,orthographic）
        # 暂时使用默认值初始化，会在update_camera_config中更新
        self.camera_config = {
            'position': np.array([0.0, 0.0, 15.0]),  # 默认位置
            'view': np.eye(4),                       # 单位矩阵
            'projection': np.eye(4),                 # 单位矩阵
            'viewport': (0, 0, 100, 100),            # 默认视口
            'orthographic': False                    # 默认为透视投影
        }
        
        self.dragging = False
        self.active_axis = None
        self.last_mouse_pos = QPoint()
        # 新增相机方向向量
        self.camera_front = np.array([0.0, 0.0, -1.0])  # 初始前向
        self.camera_right = np.array([1.0, 0.0, 0.0])    # 初始右向
        self.camera_config = self.get_camera_config()
        # 射线绘制
        self.ray_origin = None     # 射线起点（世界坐标）
        self.ray_direction = None  # 射线方向向量
        self.ray_hit_point = None  # 命中点坐标
        # 修改Raycaster初始化方式
        self.raycaster = GeometryRaycaster(
            camera_config=self.camera_config,
            geometries=self.geometries  # 直接引用主场景的物体列表
        )
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        
        # 添加鼠标按键状态跟踪
        self.left_button_pressed = False
        self.right_button_pressed = False
        self.is_dragging_view = False  # 标记是否在拖拽视角
        
        # 添加悬浮坐标系信息
        self.gizmo_info = None
        
        # 悬浮坐标系属性
        self.gizmo_cylinders = []
        self._dragging_floating_gizmo = False
        self.gizmo_geometries = []
        
        # 启用拖放
        self.setAcceptDrops(True)
        
        # 拖放预览
        self.drag_preview = {'active': False}

    def initializeGL(self):
        try:
            # 移除原有glutInit调用
            glutInit([])  # 使用空列表避免参数冲突
            glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)
            
            # 其他OpenGL初始化
            glEnable(GL_DEPTH_TEST)
            glDepthFunc(GL_LEQUAL)  # 使用小于等于比较
            glClearColor(0.1, 0.1, 0.1, 1.0)
            glEnable(GL_LIGHTING)
            glEnable(GL_LIGHT0)
            glLightfv(GL_LIGHT0, GL_POSITION, (5.0, 5.0, 5.0, 1.0))

            # 新增光照初始化[2](@ref)
            glEnable(GL_LIGHTING)
            glEnable(GL_LIGHT0)
            glLightfv(GL_LIGHT0, GL_POSITION, (5, 5, 5, 1))
            glLightfv(GL_LIGHT0, GL_DIFFUSE, (0.8, 0.8, 0.8, 1))
            
            # 地面材质
            glMaterialfv(GL_FRONT, GL_AMBIENT_AND_DIFFUSE, (0.3,0.3,0.3,1))
            
            # 新增投影矩阵设置
            glMatrixMode(GL_PROJECTION)
            gluPerspective(45, self.width()/self.height(), 0.1, 100.0)
            glMatrixMode(GL_MODELVIEW)        
        except Exception as e:
            QMessageBox.critical(None, "OpenGL Error", str(e))
            sys.exit(1)
        
        # 确保相机配置与OpenGL状态一致
        self.update_camera_config()

    def resizeGL(self, w, h):
        """窗口尺寸变化时更新相机配置和OpenGL视口"""
        # 设置OpenGL视口
        glViewport(0, 0, w, h)
        
        # 使用统一的更新方法
        self.update_camera_config()
        
        # 检查相机配置与OpenGL状态的一致性
        self.check_camera_consistency()

    def paintGL(self):
        """绘制OpenGL场景"""
        # 清除缓冲区
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        # 设置相机
        eye_pos = self.camera_config['position']
        gluLookAt(*eye_pos, *self._camera_target, 0, 0, 1)
        
        # 1. 绘制基础场景元素
        # 绘制无限网格（在坐标轴之前）
        self.draw_infinite_grid()
        # 绘制无限坐标轴（在网格之后）
        self.draw_infinite_axes()
        
        # 2. 绘制非选中物体
        for geo in self.geometries:
            if geo != self.selected_geo:
                # 绘制几何体
                self.draw_geometry(geo)
                # 绘制包围盒
                self.draw_aabb(geo)
        
        # 3. 绘制选中物体（带特效）
        if self.selected_geo:
            # 3.1 绘制选中物体的轮廓
            self.draw_outline(self.selected_geo)
            
            # 3.2 绘制半透明的选中物体
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            self.draw_geometry(self.selected_geo, alpha=0.4)
            glDisable(GL_BLEND)
            
            # 3.3 绘制高亮的包围盒
            self.draw_aabb(self.selected_geo, highlight=True)
            
            # 3.4 绘制右上方悬浮坐标系
            self.draw_floating_gizmo(self.selected_geo)
            
            # 3.5 在非观察模式下绘制变换控制器
            if self.current_mode != OperationMode.MODE_OBSERVE:
                self.draw_gizmo()
        
        # 4. 绘制调试信息（如果有）
        # 绘制射线（如果存在）
        if self.ray_origin is not None:
            self._draw_ray()
        
        # 5. 绘制网格参考线
        glBegin(GL_LINES)
        glColor3f(0.4, 0.4, 0.4)
        for x in range(-10, 11):
            glVertex3f(x, 0, -10)
            glVertex3f(x, 0, 10)
        for z in range(-10, 11):
            glVertex3f(-10, 0, z)
            glVertex3f(10, 0, z)
        glEnd()
        
        # 6. 绘制拖放预览（如果正在进行拖放操作）
        if hasattr(self, 'drag_preview') and self.drag_preview.get('active') and self.drag_preview.get('position') is not None:
            self._draw_drag_preview()

    def draw_geometry(self, geo, alpha=1.0, parent_transform=None):
        """绘制几何体"""
        if not geo:  # 增加空值保护
            return
        
        glPushMatrix()
        
        # 如果有父级变换矩阵，先应用它
        if parent_transform is not None:
            glMultMatrixf(parent_transform.T.flatten())
        
        # 应用几何体自身的变换
        glTranslatef(*geo.position)
        glRotatef(geo.rotation[0], 1, 0, 0)
        glRotatef(geo.rotation[1], 0, 1, 0)
        glRotatef(geo.rotation[2], 0, 0, 1)
        
        # 设置颜色和材质
        if hasattr(geo, 'material') and hasattr(geo.material, 'color') and len(geo.material.color) >= 3:
            r, g, b = geo.material.color[:3]
        else:
            r, g, b = 0.7, 0.7, 0.7  # 默认灰色
        
        # 设置颜色和透明度
        glColor4f(r, g, b, alpha)
        
        # 应用材质属性
        if hasattr(geo, 'material'):
            glMaterialfv(GL_FRONT, GL_DIFFUSE, [r, g, b, alpha])
            glMaterialfv(GL_FRONT, GL_SPECULAR, geo.material.specular)
            glMaterialf(GL_FRONT, GL_SHININESS, geo.material.shininess)
        
        # Mujoco的size是半长半宽半高，绘制时需要乘以2
        mujoco_size = geo.size * 2.0  # 调整尺寸
        
        # 根据几何体类型绘制
        if geo.type == GeometryType.BOX:
            # 绘制立方体
            glScalef(*mujoco_size)  # 使用调整后的尺寸
            glutSolidCube(1.0)  # 单位立方体
            
        elif geo.type == GeometryType.SPHERE:
            # 绘制球体 - 直接使用原始size，因为它是半径
            glutSolidSphere(geo.size[0], 32, 32)
            
        elif geo.type == GeometryType.ELLIPSOID:
            # 绘制椭球体 - 三个轴的半径
            glScalef(*geo.size)  # 使用原始size
            glutSolidSphere(1.0, 32, 32)  # 单位球体
            
        elif geo.type == GeometryType.CYLINDER:
            # 绘制圆柱体 - 半径和全高
            radius = geo.size[0]
            height = geo.size[1] * 2  # 全高
            glRotatef(90, 1, 0, 0)  # 旋转使Z轴朝上
            glutSolidCylinder(radius, height, 32, 32)
            
        elif geo.type == GeometryType.CAPSULE:
            # 绘制胶囊体
            radius = geo.size[0]
            half_height = geo.size[1]
            
            # 创建二次曲面对象
            quad = gluNewQuadric()
            
            # 绘制圆柱体部分
            glPushMatrix()
            glTranslatef(0, 0, -half_height)  # 移到圆柱体底部
            glRotatef(90, 1, 0, 0)  # 旋转使主轴沿Z方向
            gluCylinder(quad, radius, radius, 2 * half_height, 32, 32)
            glPopMatrix()
            
            # 绘制底部半球
            glPushMatrix()
            glTranslatef(0, 0, -half_height)
            glRotatef(-90, 1, 0, 0)
            gluSphere(quad, radius, 32, 32)
            glPopMatrix()
            
            # 绘制顶部半球
            glPushMatrix()
            glTranslatef(0, 0, half_height)
            glRotatef(90, 1, 0, 0)
            gluSphere(quad, radius, 32, 32)
            glPopMatrix()
            
            # 删除二次曲面对象
            gluDeleteQuadric(quad)
            
        elif geo.type == GeometryType.PLANE:
            # 绘制平面 - 使用调整后的尺寸
            glScalef(mujoco_size[0], mujoco_size[1], mujoco_size[2])
            glutSolidCube(1.0)  # 缩放的立方体表示平面
        
        # 如果是选中状态，绘制轮廓
        if hasattr(geo, 'selected') and geo.selected:
            self.draw_outline(geo)
        
        glPopMatrix()

    def draw_gizmo(self):
        """绘制选中物体的变换工具"""
        if not self.selected_geo:
            return
        
        try:
            # 获取物体位置
            position = np.array(self.selected_geo.position, dtype=np.float32)
            
            # 计算坐标轴长度（根据相机距离动态调整）
            camera_pos = np.array(self.camera_config.get('position', [0, 0, 0]), dtype=np.float32)
            distance = np.linalg.norm(camera_pos - position)
            axis_length = distance * 0.15  # 轴长为相机距离的15%
            
            # 保存当前矩阵状态
            glPushMatrix()
            
            # 移动到物体位置
            glTranslatef(position[0], position[1], position[2])
            
            # 设置线宽
            glLineWidth(3.0)
            
            # 禁用深度测试，确保坐标轴总是可见
            glDisable(GL_DEPTH_TEST)
            
            # 绘制X轴（红色）
            glBegin(GL_LINES)
            glColor3f(1.0, 0.0, 0.0)  # 红色
            glVertex3f(0.0, 0.0, 0.0)
            glVertex3f(axis_length, 0.0, 0.0)
            glEnd()
            
            # 绘制Y轴（绿色）
            glBegin(GL_LINES)
            glColor3f(0.0, 1.0, 0.0)  # 绿色
            glVertex3f(0.0, 0.0, 0.0)
            glVertex3f(0.0, axis_length, 0.0)
            glEnd()
            
            # 绘制Z轴（蓝色）
            glBegin(GL_LINES)
            glColor3f(0.0, 0.0, 1.0)  # 蓝色
            glVertex3f(0.0, 0.0, 0.0)
            glVertex3f(0.0, 0.0, axis_length)
            glEnd()
            
            # 绘制轴端小球，以提高可见性
            if self.current_mode != OperationMode.MODE_OBSERVE:
                radius = axis_length * 0.05  # 球体半径
                
                # X轴球体
                glPushMatrix()
                glTranslatef(axis_length, 0, 0)
                glColor3f(1.0, 0.0, 0.0)
                glutSolidSphere(radius, 8, 8)
                glPopMatrix()
                
                # Y轴球体
                glPushMatrix()
                glTranslatef(0, axis_length, 0)
                glColor3f(0.0, 1.0, 0.0)
                glutSolidSphere(radius, 8, 8)
                glPopMatrix()
                
                # Z轴球体
                glPushMatrix()
                glTranslatef(0, 0, axis_length)
                glColor3f(0.0, 0.0, 1.0)
                glutSolidSphere(radius, 8, 8)
                glPopMatrix()
            
            # 恢复深度测试
            glEnable(GL_DEPTH_TEST)
            
            # 恢复线宽
            glLineWidth(1.0)
            
            # 恢复矩阵状态
            glPopMatrix()
            
        except Exception as e:
            print(f"绘制变换工具时出错: {str(e)}")

    def mousePressEvent(self, event):
        """处理鼠标按下事件"""
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.pos()
            self.left_button_pressed = True
            
            # 检查是否有物体被点击
            try:
                # 首先检查是否点击了变换轴或悬浮坐标系（仅当已有选中物体时）
                if self.selected_geo:
                    # 检查悬浮坐标系
                    self.active_axis = self.detect_floating_axis(event.pos())
                    if self.active_axis:
                        self._dragging_floating_gizmo = True
                        self.dragging = True
                        return
                        
                    # 检查变换轴
                    if self.current_mode != OperationMode.MODE_OBSERVE:
                        self.active_axis = self.detect_axis(event.pos())
                        if self.active_axis:
                            self.dragging = True
                            return
                
                # 没有点击到变换工具，尝试选择新物体
                geo = self.pick_object(event.pos())
                
                # 添加调试信息
                print(f"选中物体检测结果: {geo.name if geo else 'None'}")
                
                if geo:
                    # 点击到了物体，设置为选中状态
                    self.set_selection(geo)
                    self.is_dragging_view = False
                else:
                    # 点击空白处，取消选中
                    self.set_selection(None)
                    self.is_dragging_view = True
            
            except Exception as e:
                print(f"鼠标点击选择处理出错: {str(e)}")
                import traceback
                traceback.print_exc()
                self.is_dragging_view = True  # 出错时默认为视角拖动
        
        # 右键操作 - 准备旋转视角
        elif event.button() == Qt.RightButton:
            self.right_button_pressed = True

    def mouseMoveEvent(self, event):
        """处理鼠标移动事件，包括悬浮坐标系拖拽"""
        # 只有当鼠标按键按下时才进行操作
        if not (self.left_button_pressed or self.right_button_pressed):
            return
            
        dx = event.x() - self.last_mouse_pos.x()
        dy = event.y() - self.last_mouse_pos.y()
        
        # 处理变换轴拖拽
        if self.left_button_pressed and self.dragging and self.active_axis:
            # 判断是拖拽悬浮坐标系还是普通变换轴
            if hasattr(self, '_dragging_floating_gizmo') and self._dragging_floating_gizmo:
                self._handle_floating_axis_drag(dx, dy)
            else:
                self.handle_axis_drag(dx, dy)
        # 处理视角平移（左键拖动空白处）
        elif self.left_button_pressed and self.is_dragging_view:
            self.handle_view_pan(dx, dy)
        # 处理相机旋转（右键拖动）    
        elif self.right_button_pressed:
            self.handle_camera_rotate(dx, dy)
        
        self.last_mouse_pos = event.pos()
        self.update()  # 触发重绘

    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件，清除拖拽状态"""
        if event.button() == Qt.LeftButton:
            self.left_button_pressed = False
            self.is_dragging_view = False
            self.dragging = False
            self.active_axis = None
            self._dragging_floating_gizmo = False
        elif event.button() == Qt.RightButton:
            self.right_button_pressed = False
        
        # 释放鼠标后不执行任何额外操作

    def handle_view_pan(self, dx, dy):
        """视角平移 - 使用统一相机配置"""
        # 获取所需的相机参数
        camera_position = self.camera_config['position']
        view_matrix = self.camera_config['view']
        
        # 获取相机坐标系的右向量和上向量（从view矩阵提取）
        right = view_matrix[:3, 0]  # 第一列是右向量
        up = view_matrix[:3, 1]     # 第二列是上向量
        
        # 计算平移缩放因子
        scale_factor = 0.005 * np.linalg.norm(camera_position - self._camera_target)
        
        # 计算平移向量
        pan_vector = right * (-dx * scale_factor) + up * (dy * scale_factor)
        
        # 更新相机目标点
        self._camera_target += pan_vector
        
        # 更新相机配置
        self.update_camera_config()

    def wheelEvent(self, event):
        """优化的鼠标滚轮事件 - 缩放视角"""
        # 获取滚轮增量并调整灵敏度
        delta = event.angleDelta().y()
        
        # 判断是否按下了修饰键
        modifiers = QApplication.keyboardModifiers()
        
        # 按下Shift键时，细微调整（更高精度）
        if modifiers == Qt.ShiftModifier:
            zoom_factor = 0.0005
        # 按下Ctrl键时，快速调整（粗调）
        elif modifiers == Qt.ControlModifier:
            zoom_factor = 0.002
        # 默认缩放速度
        else:
            zoom_factor = 0.001
        
        # 计算缩放值
        zoom_value = delta * zoom_factor
        
        # 获取鼠标位置
        mouse_pos = event.pos()
        
        # 基于当前相机距离调整缩放行为
        if self._camera_radius < 10:
            # 近距离时减小缩放速度，实现精细调整
            zoom_value *= 0.5
        elif self._camera_radius > 30:
            # 远距离时增加缩放速度，加快大范围移动
            zoom_value *= 1.5
        
        # 计算缩放后的新半径
        new_radius = self._camera_radius * (1 - zoom_value)
        
        # 限制缩放范围
        self._camera_radius = np.clip(new_radius, 0.5, 100)
        
        # 根据鼠标位置执行"缩放到光标"操作
        if modifiers == Qt.AltModifier:
            # 获取鼠标下的点（如果有物体）
            result = self.raycaster.cast_ray((mouse_pos.x(), mouse_pos.y()))
            if result and result.geometry:
                # 调整相机目标点向射线命中点移动一小步
                # 这会在缩放时同时平移相机，产生"缩放到光标"的效果
                move_factor = 0.2 * zoom_value  # 移动速度因子
                if zoom_value > 0:  # 缩小时
                    self._camera_target = self._camera_target * (1 - move_factor) + result.world_position * move_factor
                else:  # 放大时
                    # 放大时向鼠标点移动得更快些
                    self._camera_target = self._camera_target * (1 - move_factor * 2) + result.world_position * move_factor * 2
        
        # 更新相机配置
        self.update_camera_config()
        self.update()  # 触发重绘

    def set_selection(self, geo):
        """设置当前选中的几何体"""
        try:
            # 如果之前有选中的物体，取消其选中状态
            if self.selected_geo:
                self.selected_geo.selected = False
                
            self.selected_geo = geo
            
            # 设置新选中物体的状态
            if geo:
                geo.selected = True
                print(f"已选中物体: {geo.name}")
            else:
                print("已取消选中")
                
            # 发出选择变更信号
            self.selection_changed.emit(geo)
            
            # 更新显示
            self.update()
            
        except Exception as e:
            print(f"设置选中物体时出错: {str(e)}")
            import traceback
            traceback.print_exc()

    def handle_camera_rotate(self, dx, dy):
        """相机旋转 - 更新球坐标参数"""
        self._camera_phi += dx * 0.3
        self._camera_theta -= dy * 0.3
        self._camera_theta = np.clip(self._camera_theta, 1, 179)
        
        # 更新相机配置
        self.update_camera_config()

    def pick_object(self, mouse_pos: QPoint):
        """拾取物体"""
        # 转换鼠标位置为OpenGL窗口坐标
        result = self.raycaster.cast_ray((mouse_pos.x(), mouse_pos.y()))
        
        if result:
            # 更新射线数据
            self.ray_origin = result.ray_origin
            self.ray_direction = result.ray_direction
            self.ray_hit_point = result.world_position if result.geometry else None
        else:
            # 如果射线投射没有结果，清除射线数据
            self.ray_origin = None
            self.ray_direction = None
            self.ray_hit_point = None
        
        if result and result.geometry:
            print(f"选中物体：{result.geometry.name} | 碰撞点：{result.world_position}")
            return result.geometry
        
        return None

    def _pick_in_group(self, group, ray_origin, ray_direction, transform=None):
        """递归检查组内几何体，返回(命中对象, 距离)元组"""
        # 初始化为无命中
        closest_obj = None
        closest_distance = float('inf')
        
        # 获取组的世界变换
        if transform is None:
            group_transform = group.transform_matrix
        else:
            # 累积变换（如果是嵌套组）
            group_transform = transform @ group.transform_matrix
        
        # 递归检查所有子对象
        for child in group.children:
            if child.type == "group":
                # 递归检查子组
                child_result = self._pick_in_group(child, ray_origin, ray_direction, group_transform)
                # 确保结果是有效的元组
                if child_result and isinstance(child_result, tuple) and len(child_result) == 2:
                    obj, distance = child_result
                    if obj and distance < closest_distance:
                        closest_distance = distance
                        closest_obj = obj
            else:
                # 检查几何体（考虑组的变换）
                hit, distance = self._check_geometry_hit(child, ray_origin, ray_direction, group_transform)
                if hit and distance < closest_distance:
                    closest_distance = distance
                    closest_obj = child
        
        # 确保始终返回元组
        return (closest_obj, closest_distance)

    def _check_geometry_hit(self, geo, ray_origin, ray_direction, transform=None):
        """检查射线与几何体的交点"""
        try:
            # 验证输入参数
            if ray_origin is None or ray_direction is None:
                print("射线参数无效")
                return None
                
            if any(np.isnan(ray_origin)) or any(np.isnan(ray_direction)):
                print("射线包含NaN值")
                return None
                
            # 获取物体的变换矩阵
            if transform is not None:
                world_transform = transform
            elif hasattr(geo, 'get_world_transform'):
                world_transform = geo.get_world_transform()
            else:
                world_transform = geo.transform_matrix
                
            # 验证变换矩阵
            if any(np.isnan(world_transform.flatten())):
                print(f"{geo.name}的世界变换矩阵包含NaN值")
                return None
                
            # 计算射线在物体局部空间中的表示
            try:
                inv_transform = np.linalg.inv(world_transform)
            except np.linalg.LinAlgError:
                print(f"{geo.name}的变换矩阵不可逆")
                return None
                
            # 变换射线原点到局部空间
            local_origin_homo = np.append(ray_origin, 1.0)
            local_origin_homo = inv_transform @ local_origin_homo
            local_origin = local_origin_homo[:3] / local_origin_homo[3]
            
            # 变换射线方向（只旋转，不平移）
            local_direction = inv_transform[:3, :3] @ ray_direction
            local_direction = local_direction / np.linalg.norm(local_direction)
            
            # 根据几何体类型计算相交
            hit_distance = float('inf')
            
            if geo.type == GeometryType.BOX:
                # 立方体的大小是半长半宽半高
                bounds_min = -np.ones(3)  # 局部空间中的边界
                bounds_max = np.ones(3)
                
                # 计算每个轴上的交点参数
                t_min = np.zeros(3)
                t_max = np.zeros(3)
                
                for i in range(3):
                    if abs(local_direction[i]) < 1e-6:
                        # 射线与该轴平行
                        if local_origin[i] < bounds_min[i] or local_origin[i] > bounds_max[i]:
                            return None  # 射线在盒子外且平行于某个面
                        t_min[i] = -float('inf')
                        t_max[i] = float('inf')
                    else:
                        inv_dir = 1.0 / local_direction[i]
                        t1 = (bounds_min[i] - local_origin[i]) * inv_dir
                        t2 = (bounds_max[i] - local_origin[i]) * inv_dir
                        
                        if t1 > t2:
                            t_min[i], t_max[i] = t2, t1
                        else:
                            t_min[i], t_max[i] = t1, t2
                
                # 找到最大的t_min和最小的t_max
                t_enter = np.max(t_min)
                t_exit = np.min(t_max)
                
                # 有效的交点
                if t_enter <= t_exit and t_exit >= 0:
                    hit_t = t_enter if t_enter >= 0 else t_exit
                    hit_distance = hit_t
            
            # 其他几何体类型的相交测试...
            
            if hit_distance < float('inf'):
                return geo, hit_distance
            
            return None
            
        except Exception as e:
            print(f"检查几何体碰撞时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    
        # 在OpenGLWidget类中添加
    def get_world_pos(self, mouse_pos):
        """将屏幕坐标转换为世界坐标[1,2](@ref)"""
        winX = mouse_pos.x()
        winY = self.height() - mouse_pos.y()
        
        # 获取深度值
        glReadBuffer(GL_BACK)
        depth = glReadPixels(winX, winY, 1, 1, GL_DEPTH_COMPONENT)[0][0]
        
        # 转换坐标系
        viewport = glGetIntegerv(GL_VIEWPORT)
        modelview = glGetDoublev(GL_MODELVIEW_MATRIX)
        projection = glGetDoublev(GL_PROJECTION_MATRIX)
        return gluUnProject(winX, winY, depth, modelview, projection, viewport)

    def draw_infinite_grid(self):
        """绘制无限网格并与坐标轴融合"""
        glPushAttrib(GL_ENABLE_BIT)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        
        # 获取相机位置和方向
        eye_pos = self._camera_target + self._camera_radius * np.array([
            np.sin(np.radians(self._camera_theta)) * np.cos(np.radians(self._camera_phi)),
            np.sin(np.radians(self._camera_theta)) * np.sin(np.radians(self._camera_phi)),
            np.cos(np.radians(self._camera_theta))
        ])
        
        # 动态计算网格密度和范围（基于相机距离）
        grid_scale = max(1, int(self._camera_radius / 5))  # 每5单位增加一级密度
        major_interval = 10.0 * grid_scale
        minor_interval = 1.0 * grid_scale
        
        # 计算网格原点对齐（网页2的坐标对齐技巧）
        cam_pos = np.array(eye_pos)
        aligned_x = cam_pos[0] - (cam_pos[0] % major_interval)
        aligned_z = cam_pos[2] - (cam_pos[2] % major_interval)
        grid_extent = self._camera_radius * 2  # 可见范围
        
        # 绘制主网格线
        glLineWidth(1)
        glColor3f(0.4, 0.4, 0.4)
        self._draw_grid_lines(aligned_x, aligned_z, major_interval, grid_extent)
        
        # 绘制次网格线（更细更浅）
        glLineWidth(0.5)
        glColor3f(0.3, 0.3, 0.3)
        self._draw_grid_lines(aligned_x, aligned_z, minor_interval, grid_extent)
        
        glPopAttrib()

    def _draw_grid_lines(self, center_x, center_z, interval, extent):
        """动态生成网格线并跳过坐标轴区域"""
        line_count = int(extent / interval)
        axis_threshold = interval * 0.1  # 坐标轴区域阈值
        
        glBegin(GL_LINES)
        for i in range(-line_count, line_count+1):
            x = center_x + i * interval
            z = center_z + i * interval
            
            # X方向网格线（跳过Z轴附近）
            if abs(z) > axis_threshold:
                glVertex3f(x, 0, -extent + center_z)
                glVertex3f(x, 0, extent + center_z)
            
            # Z方向网格线（跳过X轴附近）
            if abs(x) > axis_threshold:
                glVertex3f(-extent + center_x, 0, z)
                glVertex3f(extent + center_x, 0, z)
        glEnd()

    def draw_infinite_axes(self):
        """增强版无限坐标轴（覆盖网格）"""
        glPushAttrib(GL_ENABLE_BIT)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        
        # 绘制粗轴心线（覆盖网格）
        glLineWidth(5)  # 加粗核心线段
        axis_length = 1000
        
        # X轴（红色核心）
        glColor3f(1, 0.2, 0.2)
        glBegin(GL_LINES)
        glVertex3f(-axis_length, 0, 0)
        glVertex3f(axis_length, 0, 0)
        glEnd()
        
        # Y轴（绿色核心）
        glColor3f(0.2, 1, 0.2)
        glBegin(GL_LINES)
        glVertex3f(0, -axis_length, 0)
        glVertex3f(0, axis_length, 0)
        glEnd()
        
        # Z轴（蓝色核心）
        glColor3f(0.2, 0.2, 1)
        glBegin(GL_LINES)
        glVertex3f(0, 0, -axis_length)
        glVertex3f(0, 0, axis_length)
        glEnd()
        
        # 绘制半透明外延（增强深度感知）
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glLineWidth(3)
        
        # X轴外延
        glColor4f(1, 0, 0, 0.3)
        glBegin(GL_LINES)
        glVertex3f(-axis_length, 0, 0)
        glVertex3f(axis_length, 0, 0)
        glEnd()
        
        # Y轴外延
        glColor4f(0, 1, 0, 0.3)
        glBegin(GL_LINES)
        glVertex3f(0, -axis_length, 0)
        glVertex3f(0, axis_length, 0)
        glEnd()
        
        # Z轴外延
        glColor4f(0, 0, 1, 0.3)
        glBegin(GL_LINES)
        glVertex3f(0, 0, -axis_length)
        glVertex3f(0, 0, axis_length)
        glEnd()
        
        glPopAttrib()
    
    def set_operation_mode(self, mode_id):
        """根据 UI 按钮切换操作模式"""
        self.current_mode = mode_id
        
        # 模式切换时清除选中物体
        if self.current_mode == OperationMode.MODE_OBSERVE:
            self.selected_geo = None
        
        # 触发界面重绘
        self.update()

    def update_camera_vectors(self):
        """更新相机的前、右、上向量"""
        # 获取相机位置（从配置或直接计算）
        camera_position = self.camera_config['position']
        
        # 计算前向量
        self.camera_front = self._camera_target - camera_position
        self.camera_front = self.camera_front / np.linalg.norm(self.camera_front)
        
        # 计算右向量和上向量
        self.camera_right = np.cross(self.camera_front, self.world_up)
        # 防止零向量导致归一化错误
        if np.linalg.norm(self.camera_right) < 1e-6:
            # 如果相机正对上方或下方，使用一个默认的右向量
            self.camera_right = np.array([1.0, 0.0, 0.0])
        else:
            self.camera_right = self.camera_right / np.linalg.norm(self.camera_right)
        
        self.camera_up = np.cross(self.camera_right, self.camera_front)
        self.camera_up = self.camera_up / np.linalg.norm(self.camera_up)

    def keyPressEvent(self, event):
        """按键事件处理"""
        if event.key() == Qt.Key_R:
            # 重置相机参数
            self._camera_theta = self._camera_initial['theta']
            self._camera_phi = self._camera_initial['phi']
            self._camera_radius = self._camera_initial['radius']
            self._camera_target = self._camera_initial['target'].copy()
            
            # 更新相机配置
            self.update_camera_config()
        else:
            super().keyPressEvent(event)

    def add_geometry(self, geo):
        """添加几何体到场景"""
        self.geometries.append(geo)
        self.geometriesChanged.emit()
        self.update()
    
    def get_camera_config(self) -> dict:
        """生成相机配置（从球坐标系转换到统一参数）"""
        # 计算相机位置（从球坐标转换为笛卡尔坐标）
        theta = np.radians(self._camera_theta)
        phi = np.radians(self._camera_phi)
        eye_pos = self._camera_target + self._camera_radius * np.array([
            np.sin(theta) * np.cos(phi),
            np.sin(theta) * np.sin(phi),
            np.cos(theta)
        ])
        
        # 构建视图矩阵
        view_matrix = self._look_at_matrix(eye_pos, self._camera_target, self.world_up)
        
        # 构建投影矩阵
        if self.use_orthographic:
            projection_matrix = self._ortho_matrix()
        else:
            projection_matrix = self._perspective_matrix()
        
        # 返回标准化的视口格式(x, y, width, height)
        viewport = (0, 0, self.width(), self.height())
        
        # 返回统一格式的相机配置
        return {
            'position': eye_pos,
            'view': view_matrix,
            'projection': projection_matrix,
            'viewport': viewport,
            'orthographic': self.use_orthographic
        }
    
    def update_camera_config(self):
        """统一的相机配置更新方法"""
        try:
            # 保存旧配置，以便在出错时回退
            old_config = self.camera_config if hasattr(self, 'camera_config') else None
            
            # 生成新的相机配置
            new_config = self.get_camera_config()
            
            # 验证新配置的有效性
            if self._validate_camera_config(new_config):
                # 更新实例变量
                self.camera_config = new_config
                
                # 更新OpenGL矩阵以匹配配置
                self._sync_opengl_matrices()
                
                # 同步更新射线投射器
                if hasattr(self, 'raycaster'):
                    try:
                        # 使用公共接口更新射线投射器
                        self.raycaster.update_camera(self.camera_config)
                    except Exception as e:
                        print(f"更新射线投射器失败: {e}")
                        # 如果射线投射器更新失败，考虑回退相机配置
                        if old_config:
                            self.camera_config = old_config
                            return False
            else:
                # 配置无效，保留旧配置
                print("警告: 生成的相机配置无效，保留原配置")
                if old_config:
                    self.camera_config = old_config
                return False
            
            return True
            
        except Exception as e:
            print(f"更新相机配置时发生错误: {e}")
            # 出错时保留旧配置
            if old_config:
                self.camera_config = old_config
            return False

    def _sync_opengl_matrices(self):
        """将OpenGL矩阵与相机配置同步"""
        # 保存当前矩阵模式
        current_mode = glGetIntegerv(GL_MATRIX_MODE)
        
        # 设置投影矩阵
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        # 转换为OpenGL列主序格式
        proj_matrix = self.camera_config['projection'].T.flatten()
        glLoadMatrixf(proj_matrix)
        
        # 设置模型视图矩阵
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        # 转换为OpenGL列主序格式
        view_matrix = self.camera_config['view'].T.flatten()
        glLoadMatrixf(view_matrix)
        
        # 恢复原矩阵模式
        glMatrixMode(current_mode)

    def _validate_camera_config(self, config=None):
        """验证相机配置的有效性"""
        # 使用传入的配置或当前配置
        cfg = config if config is not None else self.camera_config
        
        # 检查必要的键是否存在
        required_keys = ['position', 'view', 'projection', 'viewport']
        if not all(key in cfg for key in required_keys):
            print(f"相机配置缺少必要键: {[k for k in required_keys if k not in cfg]}")
            return False
        
        # 检查位置向量
        if not isinstance(cfg['position'], np.ndarray) or cfg['position'].shape != (3,):
            print(f"相机位置格式错误: {cfg['position']}")
            return False
        
        # 检查视图矩阵
        if not isinstance(cfg['view'], np.ndarray) or cfg['view'].shape != (4, 4):
            print(f"视图矩阵格式错误: {cfg['view'].shape if isinstance(cfg['view'], np.ndarray) else type(cfg['view'])}")
            return False
        
        # 检查投影矩阵
        if not isinstance(cfg['projection'], np.ndarray) or cfg['projection'].shape != (4, 4):
            print(f"投影矩阵格式错误: {cfg['projection'].shape if isinstance(cfg['projection'], np.ndarray) else type(cfg['projection'])}")
            return False
        
        # 检查视口 - 必须是4元素的元组(x, y, width, height)
        if not isinstance(cfg['viewport'], tuple) or len(cfg['viewport']) != 4:
            print(f"视口格式错误: {cfg['viewport']}")
            return False
        
        # 确保视口各元素都是非负整数
        if not all(isinstance(v, int) and v >= 0 for v in cfg['viewport']):
            print(f"视口值无效 (需要非负整数): {cfg['viewport']}")
            return False
        
        # 检查矩阵数值的有效性
        if not np.all(np.isfinite(cfg['view'])) or not np.all(np.isfinite(cfg['projection'])):
            print("相机矩阵包含无效值(inf/nan)")
            return False
        
        # 检查视图矩阵是否奇异
        try:
            det = np.linalg.det(cfg['view'][:3, :3])
            if abs(det) < 1e-10:
                print(f"视图矩阵接近奇异: det={det}")
                return False
        except Exception as e:
            print(f"检查视图矩阵时出错: {e}")
            return False
        
        return True

    def _look_at_matrix(self, eye, target, up) -> np.ndarray:
        """生成视图矩阵（替代gluLookAt）- 修正为OpenGL兼容格式"""
        # 确保所有输入都是numpy数组
        eye = np.array(eye, dtype=np.float32)
        target = np.array(target, dtype=np.float32)
        up = np.array(up, dtype=np.float32)
        
        # 计算相机z轴朝向(与OpenGL保持一致)
        z_axis = eye - target
        # 防止零向量
        if np.linalg.norm(z_axis) < 1e-6:
            z_axis = np.array([0, 0, 1])
        else:
            z_axis = z_axis / np.linalg.norm(z_axis)
        
        # 计算相机x轴
        x_axis = np.cross(up, z_axis)
        # 防止零向量(例如当up和z_axis共线时)
        if np.linalg.norm(x_axis) < 1e-6:
            x_axis = np.array([1, 0, 0])
        else:
            x_axis = x_axis / np.linalg.norm(x_axis)
        
        # 计算相机y轴
        y_axis = np.cross(z_axis, x_axis)
        y_axis = y_axis / np.linalg.norm(y_axis)
        
        # 构建视图矩阵(OpenGL格式，列主序)
        rotation = np.eye(4, dtype=np.float32)
        rotation[0, :3] = x_axis
        rotation[1, :3] = y_axis
        rotation[2, :3] = z_axis
        
        translation = np.eye(4, dtype=np.float32)
        translation[:3, 3] = -eye
        
        # 组合旋转和平移(注意顺序)
        view_matrix = rotation @ translation
        
        return view_matrix

    def _perspective_matrix(self) -> np.ndarray:
        """透视投影矩阵"""
        fov = np.radians(45)
        aspect = self.width() / self.height()
        near, far = 0.1, 100.0
        
        return np.array([
            [1/(aspect*np.tan(fov/2)), 0, 0, 0],
            [0, 1/np.tan(fov/2), 0, 0],
            [0, 0, -(far+near)/(far-near), -2*far*near/(far-near)],
            [0, 0, -1, 0]
        ])
    
    def draw_aabb(self, geo, highlight=False):
        """绘制物体的轴对齐包围盒，可选高亮模式"""
        if not geo or not hasattr(geo, 'aabb_min') or not hasattr(geo, 'aabb_max'):
            return
            
        # 获取包围盒的最小/最大坐标
        min_point = geo.aabb_min
        max_point = geo.aabb_max
        
        # 仅在物体被选中或highlight为True时绘制包围盒
        if not geo.selected and not highlight:
            return
            
        glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT | GL_LINE_BIT)
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        # 设置颜色 - 根据高亮状态决定
        if highlight:
            glColor4f(1.0, 1.0, 0.0, 0.7)  # 高亮黄色
            glLineWidth(2.0)  # 加粗线条
        else:
            glColor4f(0.8, 0.8, 1.0, 0.3)  # 普通蓝色
            glLineWidth(1.0)
        
        # 绘制包围盒线框
        glBegin(GL_LINE_LOOP)
        glVertex3f(min_point[0], min_point[1], min_point[2])
        glVertex3f(max_point[0], min_point[1], min_point[2])
        glVertex3f(max_point[0], max_point[1], min_point[2])
        glVertex3f(min_point[0], max_point[1], min_point[2])
        glEnd()
        
        glBegin(GL_LINE_LOOP)
        glVertex3f(min_point[0], min_point[1], max_point[2])
        glVertex3f(max_point[0], min_point[1], max_point[2])
        glVertex3f(max_point[0], max_point[1], max_point[2])
        glVertex3f(min_point[0], max_point[1], max_point[2])
        glEnd()
        
        glBegin(GL_LINES)
        glVertex3f(min_point[0], min_point[1], min_point[2])
        glVertex3f(min_point[0], min_point[1], max_point[2])
        
        glVertex3f(max_point[0], min_point[1], min_point[2])
        glVertex3f(max_point[0], min_point[1], max_point[2])
        
        glVertex3f(max_point[0], max_point[1], min_point[2])
        glVertex3f(max_point[0], max_point[1], max_point[2])
        
        glVertex3f(min_point[0], max_point[1], min_point[2])
        glVertex3f(min_point[0], max_point[1], max_point[2])
        glEnd()
        
        # 如果是高亮状态，添加半透明面
        if highlight:
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
            glColor4f(1.0, 1.0, 0.0, 0.1)  # 更透明的填充色
            
            # 绘制六个面
            glBegin(GL_QUADS)
            # 前面
            glVertex3f(min_point[0], min_point[1], min_point[2])
            glVertex3f(max_point[0], min_point[1], min_point[2])
            glVertex3f(max_point[0], max_point[1], min_point[2])
            glVertex3f(min_point[0], max_point[1], min_point[2])
            
            # 后面
            glVertex3f(min_point[0], min_point[1], max_point[2])
            glVertex3f(max_point[0], min_point[1], max_point[2])
            glVertex3f(max_point[0], max_point[1], max_point[2])
            glVertex3f(min_point[0], max_point[1], max_point[2])
            
            # 左面
            glVertex3f(min_point[0], min_point[1], min_point[2])
            glVertex3f(min_point[0], max_point[1], min_point[2])
            glVertex3f(min_point[0], max_point[1], max_point[2])
            glVertex3f(min_point[0], min_point[1], max_point[2])
            
            # 右面
            glVertex3f(max_point[0], min_point[1], min_point[2])
            glVertex3f(max_point[0], max_point[1], min_point[2])
            glVertex3f(max_point[0], max_point[1], max_point[2])
            glVertex3f(max_point[0], min_point[1], max_point[2])
            
            # 上面
            glVertex3f(min_point[0], max_point[1], min_point[2])
            glVertex3f(max_point[0], max_point[1], min_point[2])
            glVertex3f(max_point[0], max_point[1], max_point[2])
            glVertex3f(min_point[0], max_point[1], max_point[2])
            
            # 下面
            glVertex3f(min_point[0], min_point[1], min_point[2])
            glVertex3f(max_point[0], min_point[1], min_point[2])
            glVertex3f(max_point[0], min_point[1], max_point[2])
            glVertex3f(min_point[0], min_point[1], max_point[2])
            glEnd()
        
        glPopAttrib()

    def _draw_ray(self):
        glDisable(GL_LIGHTING)
        glLineWidth(2.0)
        
        # 绘制基础射线（红色）
        glColor3f(1.0, 0.0, 0.0)
        glBegin(GL_LINES)
        print(self.ray_origin)

        glVertex3fv(self.ray_origin)
        glVertex3fv(self.ray_origin + self.ray_direction * 100)  # 延伸100单位
        glEnd()
        
        # 绘制命中点（绿色方块）
        if self.ray_hit_point is not None:
            glPushMatrix()
            glTranslatef(*self.ray_hit_point)
            glColor3f(0.0, 1.0, 0.0)
            glutSolidCube(0.2)  # 绘制边长为0.2的立方体
            glPopMatrix()
        
        glEnable(GL_LIGHTING)

    def detect_axis(self, mouse_pos):
        """检测鼠标是否点击到了变换轴"""
        # 首先检查是否有选中的物体
        if not self.selected_geo:
            return None
            
        try:
            # 获取变换轴的根部位置（物体的位置）
            if hasattr(self.selected_geo, 'position'):
                axis_origin = np.array(self.selected_geo.position, dtype=np.float32)
            else:
                print("警告：选中物体没有position属性")
                return None
                
            # 获取变换轴的长度（根据模式和相机距离调整）
            camera_pos = np.array(self.camera_config.get('position', [0, 0, 0]), dtype=np.float32)
            distance = np.linalg.norm(camera_pos - axis_origin)
            axis_length = distance * 0.15  # 根据相机距离调整轴长
            
            # 定义三个坐标轴的端点
            axis_end_x = axis_origin + np.array([axis_length, 0, 0], dtype=np.float32)
            axis_end_y = axis_origin + np.array([0, axis_length, 0], dtype=np.float32)
            axis_end_z = axis_origin + np.array([0, 0, axis_length], dtype=np.float32)
            
            # 获取当前视图和投影矩阵
            try:
                modelview = glGetDoublev(GL_MODELVIEW_MATRIX)
                projection = glGetDoublev(GL_PROJECTION_MATRIX)
                viewport = glGetIntegerv(GL_VIEWPORT)
            except Exception as e:
                print(f"获取OpenGL矩阵失败: {str(e)}")
                return None
                
            # 投影函数
            def safe_project(point):
                try:
                    # 将3D点投影到屏幕空间
                    screen_point = gluProject(point[0], point[1], point[2], 
                                            modelview, projection, viewport)
                    return np.array([screen_point[0], screen_point[1]], dtype=np.float32)
                except Exception as e:
                    print(f"投影失败: {str(e)}")
                    return None
            
            # 投影原点和三个轴端点到屏幕空间
            origin_screen = safe_project(axis_origin)
            
            if origin_screen is None:
                print("原点投影失败")
                return None
            
            # 投影各轴端点
            x_screen = safe_project(axis_end_x)
            y_screen = safe_project(axis_end_y)
            z_screen = safe_project(axis_end_z)
            
            if x_screen is None or y_screen is None or z_screen is None:
                print("坐标轴端点投影失败")
                return None
                
            # 获取鼠标位置
            mouse_point = np.array([mouse_pos.x(), mouse_pos.y()], dtype=np.float32)
            
            # 计算点到线的距离函数
            def point_to_line_dist(point, line_start, line_end):
                if np.array_equal(line_start, line_end):
                    return np.linalg.norm(point - line_start)
                    
                line_vec = line_end - line_start
                point_vec = point - line_start
                line_len = np.linalg.norm(line_vec)
                line_unit_vec = line_vec / line_len
                
                # 计算投影长度
                proj_len = np.dot(point_vec, line_unit_vec)
                
                # 如果投影点在线段外，返回到端点的距离
                if proj_len < 0:
                    return np.linalg.norm(point - line_start)
                elif proj_len > line_len:
                    return np.linalg.norm(point - line_end)
                    
                # 计算投影点
                proj_point = line_start + line_unit_vec * proj_len
                return np.linalg.norm(point - proj_point)
            
            # 检测鼠标是否接近任何一个坐标轴
            threshold = 15  # 像素阈值
            
            # 检查X轴
            if point_to_line_dist(mouse_point, origin_screen, x_screen) < threshold:
                return 'x'
                
            # 检查Y轴
            if point_to_line_dist(mouse_point, origin_screen, y_screen) < threshold:
                return 'y'
                
            # 检查Z轴
            if point_to_line_dist(mouse_point, origin_screen, z_screen) < threshold:
                return 'z'
                
            return None
            
        except Exception as e:
            print(f"检测坐标轴时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def handle_axis_drag(self, dx, dy):
        """处理坐标轴拖动"""
        try:
            # 使用 current_mode 而不是 operation_mode
            if self.current_mode == OperationMode.MODE_TRANSLATE:
                self._handle_translate_drag(dx, dy)
            elif self.current_mode == OperationMode.MODE_ROTATE:
                self._handle_rotate_drag(dx, dy)
            elif self.current_mode == OperationMode.MODE_SCALE:
                self._handle_scale_drag(dx, dy)
                
            # 更新显示
            self.update()
            
        except Exception as e:
            print(f"处理轴拖动时出错: {str(e)}")
            import traceback
            traceback.print_exc()

    def _handle_translate_drag(self, dx, dy):
        """处理平移拖拽，支持组和子物体一起移动"""
        if not self.selected_geo:
            return
            
        # 获取相机方向向量
        camera_pos = self.camera_config['position']
        camera_dir = self._camera_target - camera_pos
        camera_dist = np.linalg.norm(camera_dir)
        
        # 计算缩放因子（基于相机距离）
        scale_factor = 0.01 * camera_dist
        
        # 根据活动轴应用平移
        if self.active_axis == 'x':
            # 在X轴方向平移
            self.selected_geo.position[0] += dx * scale_factor
        elif self.active_axis == 'y':
            # 在Y轴方向平移
            self.selected_geo.position[1] += dx * scale_factor
        elif self.active_axis == 'z':
            # 在Z轴方向平移
            self.selected_geo.position[2] += dx * scale_factor
        
        # 如果是组，确保更新子对象的变换
        if self.selected_geo.type == "group":
            self.selected_geo._update_transform()  # 先更新自身变换矩阵
            self.selected_geo._update_children_transforms()  # 然后更新所有子对象
        
        # 确保每次操作后立即更新视图
        self.update()

    def _handle_rotate_drag(self, dx, dy):
        """处理旋转拖拽，支持组和子物体一起旋转"""
        if not self.selected_geo:
            return
            
        # 旋转速度因子
        rotation_speed = 0.5
        
        # 根据活动轴应用旋转
        if self.active_axis == 'x':
            self.selected_geo.rotation[0] += dx * rotation_speed
        elif self.active_axis == 'y':
            self.selected_geo.rotation[1] += dx * rotation_speed
        elif self.active_axis == 'z':
            self.selected_geo.rotation[2] += dx * rotation_speed
        
        # 如果是组，确保更新子对象的变换
        if self.selected_geo.type == "group":
            self.selected_geo._update_transform()  # 先更新自身变换矩阵
            self.selected_geo._update_children_transforms()  # 然后更新所有子对象
        
        # 确保每次操作后立即更新视图
        self.update()

    def _handle_scale_drag(self, dx, dy):
        """处理缩放拖拽，仅适用于几何体而非组"""
        if not self.selected_geo or self.selected_geo.type == "group":
            return  # 组不支持缩放操作
            
        # 缩放速度因子
        scale_speed = 0.01
        
        # 根据活动轴应用缩放
        if self.active_axis == 'x':
            new_scale = self.selected_geo.size[0] * (1 + dx * scale_speed)
            self.selected_geo.size[0] = max(0.1, new_scale)  # 防止缩放为负或过小
        elif self.active_axis == 'y':
            new_scale = self.selected_geo.size[1] * (1 + dx * scale_speed)
            self.selected_geo.size[1] = max(0.1, new_scale)
        elif self.active_axis == 'z':
            new_scale = self.selected_geo.size[2] * (1 + dx * scale_speed)
            self.selected_geo.size[2] = max(0.1, new_scale)
        
        # 确保每次操作后立即更新视图
        self.update()

    def check_camera_consistency(self):
        """检查相机配置与OpenGL状态的一致性"""
        # 获取当前OpenGL矩阵
        current_projection = glGetFloatv(GL_PROJECTION_MATRIX)
        current_modelview = glGetFloatv(GL_MODELVIEW_MATRIX)
        
        # 将NumPy矩阵转换为适合比较的格式(列主序)
        config_proj = self.camera_config['projection'].T.flatten()
        config_view = self.camera_config['view'].T.flatten()
        
        # 转换为列表进行比较
        gl_proj = current_projection.flatten()
        gl_view = current_modelview.flatten()
        
        # 检查矩阵差异
        proj_diff = np.mean(np.abs(gl_proj - config_proj))
        view_diff = np.mean(np.abs(gl_view - config_view))
        
        # 输出差异信息
        if proj_diff > 0.01 or view_diff > 0.01:
            print(f"警告: 相机配置与OpenGL状态不一致 (投影差异: {proj_diff:.5f}, 视图差异: {view_diff:.5f})")
            # 可以考虑自动同步
            return False
        
        # 检查与射线投射器的一致性
        if hasattr(self, 'raycaster'):
            # 这里需要假设raycaster有一个获取相机配置的方法
            # 如果没有，应该在raycaster中添加
            raycaster_camera = getattr(self.raycaster, '_camera_config', None)
            if raycaster_camera is not None:
                # 检查关键参数是否一致
                pos_diff = np.linalg.norm(raycaster_camera['position'] - self.camera_config['position'])
                if pos_diff > 0.001:
                    print(f"警告: 射线投射器相机位置与主相机不一致 (差异: {pos_diff:.5f})")
                    return False
        
        return True
    
    
    def draw_outline(self, geo):
        """绘制物体轮廓，用于突出显示选中的物体"""
        if not geo:
            return
            
        # 保存当前OpenGL状态
        glPushAttrib(GL_ALL_ATTRIB_BITS)
        
        # 禁用光照和深度写入
        glDisable(GL_LIGHTING)
        glDepthMask(GL_FALSE)
        
        # 使用线框模式
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        
        # 设置线宽和颜色
        glLineWidth(3.0)
        glColor4f(1.0, 0.8, 0.0, 1.0)  # 明亮的黄色
        
        # 缩放略大一点绘制轮廓
        glPushMatrix()
        glTranslatef(*geo.position)
        glRotatef(geo.rotation[0], 1, 0, 0)
        glRotatef(geo.rotation[1], 0, 1, 0)
        glRotatef(geo.rotation[2], 0, 0, 1)
        
        # 比原始大小略大
        scale_factor = 1.02
        if geo.type == GeometryType.BOX:
            glScalef(*(geo.size * 2.0 * scale_factor))
            glutWireCube(1.0)
        elif geo.type == GeometryType.SPHERE:
            glutWireSphere(geo.size[0] * scale_factor, 20, 20)
        elif geo.type == GeometryType.ELLIPSOID:
            glScalef(*(geo.size * scale_factor))
            glutWireSphere(1.0, 20, 20)
        elif geo.type == GeometryType.CYLINDER:
            radius = geo.size[0] * scale_factor
            height = geo.size[1] * 2 * scale_factor
            glRotatef(90, 1, 0, 0)
            glutWireCylinder(radius, height, 20, 8)
        elif geo.type == GeometryType.CAPSULE:
            radius = geo.size[0] * scale_factor
            half_height = geo.size[1] * scale_factor  # 这里是半高
            
            # 旋转为匹配MuJoCo的胶囊体方向(z轴朝上)
            glRotatef(90, 1, 0, 0)
            
            # 绘制圆柱部分 - 长度为两倍的half_height
            glutWireCylinder(radius, half_height * 2, 20, 8)
            
            # 顶部半球 - 位于圆柱体顶端
            glPushMatrix()
            glTranslatef(0, 0, half_height)
            # 绘制完整球体，只有一半会在圆柱体外部可见
            quadric = gluNewQuadric()
            gluQuadricDrawStyle(quadric, GLU_LINE)
            gluSphere(quadric, radius, 16, 8)
            gluDeleteQuadric(quadric)
            glPopMatrix()
            
            # 底部半球 - 位于圆柱体底端
            glPushMatrix()
            glTranslatef(0, 0, -half_height)
            quadric = gluNewQuadric()
            gluQuadricDrawStyle(quadric, GLU_LINE)
            gluSphere(quadric, radius, 16, 8)
            gluDeleteQuadric(quadric)
            glPopMatrix()
        
        elif geo.type == GeometryType.PLANE:
            # 绘制平面轮廓 - 更清晰地表示为网格
            width = geo.size[0] * 2 * scale_factor  # x方向尺寸
            depth = geo.size[2] * 2 * scale_factor  # z方向尺寸
            
            # 不使用glScalef，直接绘制具体尺寸的平面
            # 绘制平面边界
            glBegin(GL_LINE_LOOP)
            glVertex3f(-width/2, 0, -depth/2)
            glVertex3f(width/2, 0, -depth/2)
            glVertex3f(width/2, 0, depth/2)
            glVertex3f(-width/2, 0, depth/2)
            glEnd()
            
            # 绘制网格线
            grid_div = 4
            glBegin(GL_LINES)
            # X方向线
            for i in range(1, grid_div):
                t = i / grid_div
                z = depth * (t - 0.5)
                glVertex3f(-width/2, 0, z)
                glVertex3f(width/2, 0, z)
            
            # Z方向线
            for i in range(1, grid_div):
                t = i / grid_div
                x = width * (t - 0.5)
                glVertex3f(x, 0, -depth/2)
                glVertex3f(x, 0, depth/2)
            glEnd()
            
            # 绘制法线
            glBegin(GL_LINES)
            glVertex3f(0, 0, 0)
            glVertex3f(0, width/10, 0)  # 法线长度为平面宽度的十分之一
            glEnd()
        
        glPopMatrix()
        
        # 恢复OpenGL状态
        glPopAttrib()

    def draw_floating_gizmo(self, geo):
        """绘制不与物体重合的悬浮坐标系"""
        if not geo:
            return
        
        # 计算物体的世界坐标位置和尺寸
        obj_pos = geo.position
        obj_size = np.max(geo.size)
        
        # 确定坐标系的位置 - 距离物体一定距离
        # 使用相机配置确定最佳位置
        camera_pos = self.camera_config['position']
        camera_dir = self._camera_target - camera_pos
        
        # 计算相机到物体的方向
        to_obj_dir = obj_pos - camera_pos
        to_obj_dist = np.linalg.norm(to_obj_dir)
        
        # 更新相机向量
        self.update_camera_vectors()
        
        # 使用相机的右向量确定坐标系的位置
        offset_distance = max(obj_size * 2.5, 1.0)  # 确保距离足够
        
        # 坐标系位置 - 物体右上角，考虑相机角度
        gizmo_pos = obj_pos + self.camera_right * offset_distance + np.array([0, 0, offset_distance * 0.5])
        
        # 让坐标系保持在物体附近，但不与物体重叠
        # 如果物体太大，可能需要调整位置
        if geo.type == GeometryType.PLANE:
            # 平面通常很大，坐标系放在上方
            gizmo_pos = obj_pos + np.array([0, 0, offset_distance])
        
        # 坐标轴的长度和粗细
        axis_length = max(0.5, obj_size * 0.8)
        axis_thickness = axis_length * 0.08  # 轴的粗细
        
        # 禁用深度测试，确保坐标系总是可见
        glDisable(GL_DEPTH_TEST)
        
        # 绘制并保存坐标系信息，用于拖拽检测
        self.gizmo_geometries = []
        
        # 绘制坐标系原点（小球）
        glPushMatrix()
        glTranslatef(*gizmo_pos)
        
        # 禁用光照以便更清晰地显示坐标轴
        glDisable(GL_LIGHTING)
        
        # 原点球
        glColor3f(0.8, 0.8, 0.8)
        glutSolidSphere(axis_thickness * 1.5, 12, 12)
        
        # X轴 - 红色
        glColor3f(1.0, 0.0, 0.0)
        x_end = gizmo_pos + np.array([axis_length, 0, 0])
        self._draw_axis_cylinder(gizmo_pos[0], gizmo_pos[1], gizmo_pos[2], 
                                x_end[0], x_end[1], x_end[2], axis_thickness)
        # 保存X轴几何信息
        x_axis_geo = Geometry(
            geo_type=GeometryType.CYLINDER,
            name="gizmo_x_axis",
            position=(gizmo_pos + x_end) / 2,  # 中点
            size=[axis_thickness, axis_length/2, 0],  # 半径和半高
            rotation=[0, 90, 0]  # 旋转使圆柱体沿X轴
        )
        x_axis_geo.material.color = [1.0, 0.0, 0.0, 1.0]  # 红色
        self.gizmo_geometries.append(('x', x_axis_geo))
        
        # Y轴 - 绿色
        glColor3f(0.0, 1.0, 0.0)
        y_end = gizmo_pos + np.array([0, axis_length, 0])
        self._draw_axis_cylinder(gizmo_pos[0], gizmo_pos[1], gizmo_pos[2], 
                                y_end[0], y_end[1], y_end[2], axis_thickness)
        # 保存Y轴几何信息
        y_axis_geo = Geometry(
            geo_type=GeometryType.CYLINDER,
            name="gizmo_y_axis",
            position=(gizmo_pos + y_end) / 2,  # 中点
            size=[axis_thickness, axis_length/2, 0],  # 半径和半高
            rotation=[90, 0, 0]  # 旋转使圆柱体沿Y轴
        )
        y_axis_geo.material.color = [0.0, 1.0, 0.0, 1.0]  # 绿色
        self.gizmo_geometries.append(('y', y_axis_geo))
        
        # Z轴 - 蓝色
        glColor3f(0.0, 0.0, 1.0)
        z_end = gizmo_pos + np.array([0, 0, axis_length])
        self._draw_axis_cylinder(gizmo_pos[0], gizmo_pos[1], gizmo_pos[2], 
                                z_end[0], z_end[1], z_end[2], axis_thickness)
        # 保存Z轴几何信息
        z_axis_geo = Geometry(
            geo_type=GeometryType.CYLINDER,
            name="gizmo_z_axis",
            position=(gizmo_pos + z_end) / 2,  # 中点
            size=[axis_thickness, axis_length/2, 0],  # 半径和半高
            rotation=[0, 0, 0]  # Z轴不需要旋转
        )
        z_axis_geo.material.color = [0.0, 0.0, 1.0, 1.0]  # 蓝色
        self.gizmo_geometries.append(('z', z_axis_geo))
        
        # 绘制坐标轴标签
        glRasterPos3f(x_end[0] + axis_thickness * 2, x_end[1], x_end[2])
        # 使用GLUT绘制文字
        # 这里通常会使用glutBitmapCharacter绘制"X"，但需要确保GLUT已初始化
        
        # 恢复设置
        glEnable(GL_LIGHTING)
        glEnable(GL_DEPTH_TEST)
        glPopMatrix()
        
        # 存储坐标系的位置信息，供拖拽使用
        self.gizmo_pos = gizmo_pos

    def _draw_axis_cylinder(self, x1, y1, z1, x2, y2, z2, radius):
        """绘制单个坐标轴的圆柱体"""
        # 计算方向向量
        dx = x2 - x1
        dy = y2 - y1
        dz = z2 - z1
        
        # 计算长度
        length = np.sqrt(dx*dx + dy*dy + dz*dz)
        if length < 0.0001:
            return
        
        # 计算旋转角度，使圆柱体对齐到目标方向
        if abs(dx) > 0.0001 or abs(dy) > 0.0001:
            # 对于非垂直于XY平面的圆柱体
            # 计算在XY平面上的投影与X轴的夹角
            angle1 = np.degrees(np.arctan2(dy, dx))
            # 计算与Z轴的夹角
            angle2 = np.degrees(np.arccos(dz/length))
            
            glPushMatrix()
            # 旋转到目标方向
            glRotatef(angle1, 0, 0, 1)  # 先绕Z轴旋转
            glRotatef(angle2, 0, 1, 0)  # 再绕Y轴旋转
            glutSolidCylinder(radius, length, 8, 2)  # 简化多边形数量提高性能
            
            # 绘制箭头（锥体）
            glTranslatef(0, 0, length)
            glutSolidCone(radius*1.8, radius*4, 8, 2)
            
            glPopMatrix()
        else:
            # 对于平行于Z轴的圆柱体，直接绘制
            glPushMatrix()
            if dz > 0:
                # Z轴正方向
                glutSolidCylinder(radius, length, 8, 2)
                glTranslatef(0, 0, length)
                glutSolidCone(radius*1.8, radius*4, 8, 2)
            else:
                # Z轴负方向
                glRotatef(180, 1, 0, 0)
                glutSolidCylinder(radius, length, 8, 2)
                glTranslatef(0, 0, length)
                glutSolidCone(radius*1.8, radius*4, 8, 2)
            glPopMatrix()

    def detect_floating_axis(self, mouse_pos):
        """使用Raycaster检测悬浮坐标系的点击"""
        if not self.selected_geo or not hasattr(self, 'gizmo_geometries'):
            return None
    
        try:
            # 创建临时射线投射器
            temp_raycaster = GeometryRaycaster(
                camera_config=self.camera_config,
                geometries=[geo for _, geo in self.gizmo_geometries]
            )
            
            # 投射射线检测碰撞
            result = temp_raycaster.cast_ray((mouse_pos.x(), mouse_pos.y()))
            
            if result and result.geometry:
                # 找到对应的轴名称
                for axis_name, geo in self.gizmo_geometries:
                    if result.geometry == geo:
                        return axis_name
            
            return None
        
        except Exception as e:
            print(f"检测悬浮坐标系出错: {str(e)}")
            return None

    def _ray_cylinder_intersection(self, ray_origin, ray_direction, cylinder_start, cylinder_end, radius):
        """射线与圆柱体相交检测"""
        # 圆柱体轴向向量
        cylinder_axis = cylinder_end - cylinder_start
        axis_length = np.linalg.norm(cylinder_axis)
        if axis_length < 0.0001:
            return None
        
        cylinder_axis = cylinder_axis / axis_length
        
        # 计算射线与圆柱体轴的最近点
        oc = ray_origin - cylinder_start
        
        # 圆柱体轴与射线的垂直分量
        axis_dot_dir = np.dot(cylinder_axis, ray_direction)
        axis_dot_oc = np.dot(cylinder_axis, oc)
        
        # 计算二次方程参数
        a = 1.0 - axis_dot_dir * axis_dot_dir
        b = 2.0 * (np.dot(ray_direction, oc) - axis_dot_dir * axis_dot_oc)
        c = np.dot(oc, oc) - axis_dot_oc * axis_dot_oc - radius * radius
        
        # 检查射线是否与圆柱体相交
        discriminant = b * b - 4 * a * c
        
        if discriminant < 0:
            return None
        
        # 计算相交点距离
        t = (-b - np.sqrt(discriminant)) / (2 * a)
        if t < 0:
            # 尝试另一个解
            t = (-b + np.sqrt(discriminant)) / (2 * a)
            if t < 0:
                return None
        
        # 计算相交点
        hit_point = ray_origin + t * ray_direction
        
        # 检查相交点是否在圆柱体长度范围内
        hit_to_start = hit_point - cylinder_start
        projection = np.dot(hit_to_start, cylinder_axis)
        
        if projection < 0 or projection > axis_length:
            return None
        
        # 返回相交点信息
        return {
            'distance': t,
            'point': hit_point
        }

    def _get_mouse_ray(self, mouse_pos):
        """获取从相机通过鼠标点的射线"""
        try:
            # 获取当前的视口、模型视图矩阵和投影矩阵
            viewport = glGetIntegerv(GL_VIEWPORT)
            modelview = glGetDoublev(GL_MODELVIEW_MATRIX)
            projection = glGetDoublev(GL_PROJECTION_MATRIX)
            
            # 获取鼠标点在视口中的坐标
            x = float(mouse_pos.x())
            y = float(viewport[3] - mouse_pos.y())  # 翻转Y坐标
            
            print(f"视口: {viewport}")
            print(f"鼠标坐标: ({x}, {y})")
            
            try:
                # 获取近平面和远平面上的点
                near_point = gluUnProject(x, y, 0.0, modelview, projection, viewport)
                far_point = gluUnProject(x, y, 1.0, modelview, projection, viewport)
                
                if near_point is None or far_point is None:
                    print("警告: gluUnProject返回None")
                    return None, None
                    
                # 转换为numpy数组
                near_point = np.array(near_point, dtype=np.float32)
                far_point = np.array(far_point, dtype=np.float32)
                
                # 检查结果有效性
                if any(np.isnan(near_point)) or any(np.isnan(far_point)):
                    print(f"警告: 投影结果包含NaN值, 近点: {near_point}, 远点: {far_point}")
                    return None, None
                    
                print(f"近点: {near_point}")
                print(f"远点: {far_point}")
                    
                # 计算射线方向
                ray_direction = far_point - near_point
                ray_length = np.linalg.norm(ray_direction)
                
                # 归一化方向向量
                if ray_length < 1e-6:
                    print(f"警告: 射线长度太小: {ray_length}")
                    return None, None
                    
                ray_direction = ray_direction / ray_length
                
                return near_point, ray_direction
                
            except Exception as e:
                print(f"UnProject计算出错: {str(e)}")
                import traceback
                traceback.print_exc()
                return None, None
                
        except Exception as e:
            print(f"获取鼠标射线时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return None, None

    def _handle_floating_axis_drag(self, dx, dy):
        """处理悬浮坐标系拖拽，利用轴方向移动物体"""
        if not self.selected_geo or not self.active_axis:
            return
        
        # 获取相机参数计算移动系数
        camera_pos = self.camera_config['position']
        camera_dist = np.linalg.norm(camera_pos - self._camera_target)
        
        # 根据相机距离和物体大小调整移动速度
        obj_size = np.max(self.selected_geo.size)
        move_scale = 0.01 * camera_dist * max(1.0, obj_size)
        
        # 找到当前拖拽的轴
        axis_direction = None
        for axis_name, geo in self.gizmo_geometries:
            if axis_name == self.active_axis:
                # 根据坐标轴类型确定方向
                if axis_name == 'x':
                    axis_direction = np.array([1.0, 0.0, 0.0])
                elif axis_name == 'y':
                    axis_direction = np.array([0.0, 1.0, 0.0])
                elif axis_name == 'z':
                    axis_direction = np.array([0.0, 0.0, 1.0])
                break
        
        if axis_direction is None:
            return
        
        # 获取相机视角方向
        self.update_camera_vectors()
        
        # 使用正确的相机方向向量
        view_right = self.camera_right
        # 通过camera_front和camera_right的叉积计算up向量
        view_up = np.cross(self.camera_right, self.camera_front)
        # 归一化向量
        if np.linalg.norm(view_up) > 0:
            view_up = view_up / np.linalg.norm(view_up)
        
        # 计算鼠标移动在轴方向上的投影
        drag_vector = dx * view_right + (-dy) * view_up  # 注意y轴方向
        projection = np.dot(drag_vector, axis_direction)
        
        # 根据投影移动物体
        move_amount = projection * move_scale
        
        # 更新物体位置
        self.selected_geo.position += axis_direction * move_amount

    def dragEnterEvent(self, event):
        """处理拖拽进入事件"""
        # 检查是否是几何体类型数据
        if event.mimeData().hasText():
            event.acceptProposedAction()
            # 显示拖放预览
            self.drag_preview = {
                'active': True,
                'position': np.array([0.0, 0.0, 0.0]),  # 提供默认值
                'type': event.mimeData().text()
            }
            self.update()

    def dragLeaveEvent(self, event):
        """处理拖拽离开事件"""
        # 清除拖放预览
        self.drag_preview = {'active': False}
        self.update()

    def dragMoveEvent(self, event):
        """处理拖拽移动事件，更新预览位置"""
        event.acceptProposedAction()
        
        # 更新预览位置
        if hasattr(self, 'drag_preview') and self.drag_preview['active']:
            pos = self._get_drop_position(event.pos())
            if pos is not None:  # 确保位置有效
                self.drag_preview['position'] = pos
                self.update()

    def dropEvent(self, event):
        """处理拖拽放置事件"""
        # 获取拖放位置
        mouse_pos = event.pos()
        
        # 获取几何体类型
        geo_type = event.mimeData().text()
        
        # 获取3D世界中的放置位置
        world_pos = self._get_drop_position(mouse_pos)
        
        # 创建并添加几何体 (world_pos 总是会返回有效值，不会是None)
        self._add_geometry_at_position(geo_type, world_pos)
        
        event.acceptProposedAction()

    def _get_drop_position(self, mouse_pos):
        """计算拖放位置在3D空间中的坐标"""
        try:
            # 先获取鼠标射线
            ray_result = self._get_mouse_ray(mouse_pos)
            if ray_result is None:
                # 如果无法获取射线，返回默认位置
                print("无法获取射线，使用默认位置")
                return np.array([0.0, 0.0, 0.0])
            
            near_point, ray_direction = ray_result
            
            # 检查是否有物体在鼠标位置
            # 创建临时射线投射器检测碰撞
            temp_raycaster = GeometryRaycaster(
                camera_config=self.camera_config,
                geometries=self.geometries
            )
            
            # 转换为元组格式传递给raycaster
            if isinstance(mouse_pos, QPoint):
                cast_pos = (mouse_pos.x(), mouse_pos.y())
            else:
                cast_pos = mouse_pos  # 假设已经是元组
                
            result = temp_raycaster.cast_ray(cast_pos)
            if result and result.geometry:
                # 如果射线击中了物体，返回击中点
                return result.world_position
            
            # 如果没有击中物体，放置在地面上(y=0平面)
            plane_y = 0
            
            # 计算与地面的交点
            if abs(ray_direction[1]) > 1e-6:  # 避免除以零
                t = (plane_y - near_point[1]) / ray_direction[1]
                if t > 0:  # 确保在射线前方
                    intersection = near_point + t * ray_direction
                    return intersection
            
            # 如果无法计算交点，返回默认位置
            return np.array([0.0, 0.0, 0.0])
        
        except Exception as e:
            print(f"计算拖放位置出错: {str(e)}")
            return np.array([0.0, 0.0, 0.0])  # 返回默认位置而不是None

    def _add_geometry_at_position(self, geo_type, position):
        """在指定位置创建几何体"""
        # 为不同类型设置合适的默认尺寸（半长半宽半高）
        default_sizes = {
            GeometryType.BOX: (0.5, 0.5, 0.5),         # 半长半宽半高
            GeometryType.SPHERE: (0.5, 0.5, 0.5),      # 半径
            GeometryType.ELLIPSOID: (0.6, 0.4, 0.3),   # 三轴半径
            GeometryType.CYLINDER: (0.5, 0.5, 0.5),    # 半径, 半高
            GeometryType.CAPSULE: (0.5, 0.5, 0.5),     # 半径, 半高
            GeometryType.PLANE: (1.0, 1.0, 0.05)       # 半宽, 半长, 半厚
        }
        
        # 为不同类型设置默认名称
        type_names = {
            GeometryType.BOX: "立方体",
            GeometryType.SPHERE: "球体",
            GeometryType.ELLIPSOID: "椭球体",
            GeometryType.CYLINDER: "圆柱体",
            GeometryType.CAPSULE: "胶囊体",
            GeometryType.PLANE: "平面"
        }
        
        try:
            # 创建几何体
            count = sum(1 for geo in self.geometries if geo.type == geo_type)
            name = f"{type_names.get(geo_type, '物体')}_{count+1}"
            size = default_sizes.get(geo_type, (0.5, 0.5, 0.5))
            
            # 创建几何体对象
            geo = Geometry(
                geo_type=geo_type,
                name=name,
                position=position,
                size=size,
                rotation=(0, 0, 0)
            )
            
            # 添加到场景
            self.add_geometry(geo)
            
            # 选中新添加的几何体
            self.set_selection(geo)
            
            # 如果在观察模式，自动切换到平移模式
            if self.current_mode == OperationMode.MODE_OBSERVE:
                self.current_mode = OperationMode.MODE_TRANSLATE
                self.transform_mode_changed.emit(OperationMode.MODE_TRANSLATE)
                
        except Exception as e:
            print(f"创建几何体出错: {str(e)}")

    def _draw_drag_preview(self):
        """绘制拖放预览"""
        if not hasattr(self, 'drag_preview') or not self.drag_preview.get('active'):
            return
        
        position = self.drag_preview.get('position')
        geo_type = self.drag_preview.get('type')
        
        if position is None or geo_type is None:
            return
        
        # 设置半透明
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        # 禁用光照，使用固定颜色
        glDisable(GL_LIGHTING)
        
        # 绘制预览形状
        glPushMatrix()
        glTranslatef(*position)
        
        # 使用半透明蓝色
        glColor4f(0.3, 0.5, 0.9, 0.4)
        
        # 根据几何体类型绘制不同形状
        if geo_type == GeometryType.BOX:
            glScalef(1.0, 1.0, 1.0)  # 立方体
            glutWireCube(1.0)
        elif geo_type == GeometryType.SPHERE:
            glutWireSphere(0.5, 16, 16)  # 球体
        elif geo_type == GeometryType.CYLINDER:
            glRotatef(90, 1, 0, 0)  # 旋转使Z轴朝上
            glutWireCylinder(0.5, 1.0, 16, 2)  # 圆柱体
        elif geo_type == GeometryType.CAPSULE:
            # 使用与正式渲染相同的逻辑
            radius = 0.5  # 默认半径
            half_height = 1.0  # 默认圆柱体半高度
            
            # 只创建一次quad对象
            quad = gluNewQuadric()
            
            # 绘制预览胶囊体
            gluCylinder(quad, radius, radius, 2 * half_height, 32, 32)
            
            # 绘制底部半球
            glPushMatrix()
            glTranslatef(0, 0, -half_height)
            glRotatef(-90, 1, 0, 0)
            gluSphere(quad, radius, 32, 32)
            glPopMatrix()
            
            # 绘制顶部半球
            glPushMatrix()
            glTranslatef(0, 0, half_height)
            glRotatef(90, 1, 0, 0)
            gluSphere(quad, radius, 32, 32)
            glPopMatrix()
            
            # 所有操作完成后只释放一次
            gluDeleteQuadric(quad)
        elif geo_type == GeometryType.ELLIPSOID:
            glScalef(0.6, 0.4, 0.3)  # 椭球体
            glutWireSphere(1.0, 16, 16)
        elif geo_type == GeometryType.PLANE:
            glScalef(2.0, 0.1, 2.0)  # 平面
            glutWireCube(1.0)
        
        glPopMatrix()
        
        # 绘制放置位置标记
        glPointSize(5.0)
        glBegin(GL_POINTS)
        glVertex3f(*position)
        glEnd()
        
        # 恢复设置
        glEnable(GL_LIGHTING)
        glDisable(GL_BLEND)

    def _draw_group_recursive(self, group):
        """递归绘制组及其所有子对象，不选择组本身"""
        # 保存当前矩阵状态
        glPushMatrix()
        
        # 应用组的变换
        glTranslatef(*group.position)
        glRotatef(group.rotation[0], 1, 0, 0)
        glRotatef(group.rotation[1], 0, 1, 0)
        glRotatef(group.rotation[2], 0, 0, 1)
        
        # 绘制所有子对象
        for child in group.children:
            if isinstance(child, GeometryGroup):
                # 递归绘制子组
                self._draw_group_recursive(child)
            else:
                # 绘制子几何体
                self.draw_geometry(child)
                
                # 如果几何体被选中，绘制轮廓和gizmo
                if child.selected:
                    self.draw_outline(child)
                    self.draw_floating_gizmo(child)
        
        # 恢复矩阵状态
        glPopMatrix()
    
    def _draw_group_bounds(self, group):
        """绘制组边界框"""
        glPushAttrib(GL_ALL_ATTRIB_BITS)
        
        # 设置线宽和颜色
        glLineWidth(2.0)
        glColor4f(0.5, 0.8, 1.0, 0.7)  # 蓝色，半透明
        
        # 禁用深度测试，确保边界框总是可见
        glDisable(GL_DEPTH_TEST)
        
        # 绘制组边界框（正方体）
        size = 0.5  # 边界框大小
        
        glPushMatrix()
        
        # 绘制线框立方体
        glBegin(GL_LINES)
        # 底部正方形
        glVertex3f(-size, -size, -size)
        glVertex3f(size, -size, -size)
        
        glVertex3f(size, -size, -size)
        glVertex3f(size, -size, size)
        
        glVertex3f(size, -size, size)
        glVertex3f(-size, -size, size)
        
        glVertex3f(-size, -size, size)
        glVertex3f(-size, -size, -size)
        
        # 顶部正方形
        glVertex3f(-size, size, -size)
        glVertex3f(size, size, -size)
        
        glVertex3f(size, size, -size)
        glVertex3f(size, size, size)
        
        glVertex3f(size, size, size)
        glVertex3f(-size, size, size)
        
        glVertex3f(-size, size, size)
        glVertex3f(-size, size, -size)
        
        # 连接顶部和底部
        glVertex3f(-size, -size, -size)
        glVertex3f(-size, size, -size)
        
        glVertex3f(size, -size, -size)
        glVertex3f(size, size, -size)
        
        glVertex3f(size, -size, size)
        glVertex3f(size, size, size)
        
        glVertex3f(-size, -size, size)
        glVertex3f(-size, size, size)
        glEnd()
        
        glPopMatrix()
        
        # 恢复OpenGL状态
        glPopAttrib()
    
    def _pick_in_group(self, group, ray_origin, ray_direction, transform=None):
        """在组内拾取对象，仅选择几何体而非组"""
        # 计算组的变换矩阵
        if transform is None:
            transform = np.eye(4)
        
        # 应用组的变换
        rot_matrix = euler_angles_to_matrix(np.radians(group.rotation))
        trans_matrix = np.eye(4)
        trans_matrix[:3, 3] = group.position
        group_transform = trans_matrix @ rot_matrix
        
        # 组合变换
        combined_transform = transform @ group_transform
        
        # 修改：不检查组本身，只检查子几何体
        for child in reversed(group.children):  # 逆序检查，使前面的对象优先被选中
            if isinstance(child, GeometryGroup):
                # 递归检查子组中的几何体
                picked = self._pick_in_group(child, ray_origin, ray_direction, combined_transform)
                if picked:
                    return picked
            else:
                # 检查射线与子几何体的相交
                # 转换射线到局部坐标系
                local_start = ray_origin.copy()
                local_direction = ray_direction.copy()
                
                # 应用组的变换到射线
                center = child.position.copy()
                size = child.size.copy()
                rotation = euler_angles_to_matrix(np.radians(child.rotation))[:3, :3]
                
                # 获取世界坐标系中的位置
                world_center = np.array([0.0, 0.0, 0.0])
                world_center = combined_transform @ np.append(center, 1.0)
                world_center = world_center[:3]
                
                # 获取世界坐标系中的旋转
                world_rotation = combined_transform[:3, :3] @ rotation
                
                # 检查射线与几何体的交点
                hit_result = None
                
                if child.type == GeometryType.BOX:
                    hit_result = self.raycaster.ray_box_intersection(
                        ray_origin, ray_direction, world_center, size, world_rotation)
                elif child.type == GeometryType.SPHERE:
                    hit_result = self.raycaster.ray_sphere_intersection(
                        ray_origin, ray_direction, world_center, size, world_rotation)
                elif child.type == GeometryType.CYLINDER:
                    hit_result = self.raycaster.ray_cylinder_intersection(
                        ray_origin, ray_direction, world_center, size, world_rotation)
                elif child.type == GeometryType.ELLIPSOID:
                    hit_result = self.raycaster.ray_ellipsoid_intersection(
                        ray_origin, ray_direction, world_center, size, world_rotation)
                elif child.type == GeometryType.CAPSULE:
                    hit_result = self.raycaster.ray_capsule_intersection(
                        ray_origin, ray_direction, world_center, size, world_rotation)
                elif child.type == GeometryType.PLANE:
                    hit_result = self.raycaster.ray_plane_intersection(
                        ray_origin, ray_direction, world_center, size, world_rotation)
                
                # 如果有交点，返回这个几何体
                if hit_result is not None and hit_result[3] > 0:
                    return child
        
        # 如果没有找到任何相交的几何体，返回None
        return None

    # 添加辅助方法来递归更新选择状态
    def _update_selection_recursive(self, item, obj):
        current_obj = self.item_to_obj.get(id(item))
        if current_obj is obj:
            item.setSelected(True)
        else:
            item.setSelected(False)
        
        # 递归处理子项
        for i in range(item.childCount()):
            self._update_selection_recursive(item.child(i), obj)



# ========== 界面组件 ==========
class ControlPanel(QDockWidget):
    def __init__(self, gl_widget):
        super().__init__("控制面板")
        self.gl_widget = gl_widget
        
        # 创建控制面板主窗口
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        
        # 创建几何体类型选择框
        geo_type_group = QGroupBox("添加几何体")
        geo_type_layout = QGridLayout()
        
        # 几何体类型和名称映射
        geo_types = [
            (GeometryType.BOX, "立方体"),
            (GeometryType.SPHERE, "球体"),
            (GeometryType.ELLIPSOID, "椭球体"),
            (GeometryType.CYLINDER, "圆柱体"),
            (GeometryType.CAPSULE, "胶囊体"),
            (GeometryType.PLANE, "平面")
        ]
        
        # 创建可拖拽按钮
        row, col = 0, 0
        for geo_type, title in geo_types:
            btn = DraggableGeometryButton(geo_type, title)
            geo_type_layout.addWidget(btn, row, col)
            col += 1
            if col > 1:  # 每行两个按钮
                col = 0
                row += 1
        
        # 保留常规的下拉框和添加按钮
        row += 1
        self.geo_type_combo = QComboBox()
        self.geo_type_combo.addItems([f"{title} ({geo_type})" for geo_type, title in geo_types])
        geo_type_layout.addWidget(self.geo_type_combo, row, 0, 1, 2)
        
        row += 1
        add_btn = QPushButton("添加所选几何体")
        add_btn.clicked.connect(self.add_geometry)
        geo_type_layout.addWidget(add_btn, row, 0, 1, 2)
        
        # 添加拖拽提示标签
        row += 1
        drag_label = QLabel("提示: 拖拽按钮到3D视图中放置物体")
        drag_label.setAlignment(Qt.AlignCenter)
        drag_label.setStyleSheet("color: gray; font-style: italic;")
        geo_type_layout.addWidget(drag_label, row, 0, 1, 2)
        
        geo_type_group.setLayout(geo_type_layout)
        layout.addWidget(geo_type_group)
        
        # 操作模式选择
        mode_group = QGroupBox("操作模式")
        mode_layout = QVBoxLayout()
        
        # 添加不同的操作模式按钮
        self.observe_btn = QRadioButton("观察模式")
        self.translate_btn = QRadioButton("平移模式")
        self.rotate_btn = QRadioButton("旋转模式")
        self.scale_btn = QRadioButton("缩放模式")
        
        self.observe_btn.setChecked(True)
        
        # 连接信号
        self.observe_btn.toggled.connect(lambda: self.on_mode_changed(OperationMode.MODE_OBSERVE))
        self.translate_btn.toggled.connect(lambda: self.on_mode_changed(OperationMode.MODE_TRANSLATE))
        self.rotate_btn.toggled.connect(lambda: self.on_mode_changed(OperationMode.MODE_ROTATE))
        self.scale_btn.toggled.connect(lambda: self.on_mode_changed(OperationMode.MODE_SCALE))
        
        # 添加到布局
        mode_layout.addWidget(self.observe_btn)
        mode_layout.addWidget(self.translate_btn)
        mode_layout.addWidget(self.rotate_btn)
        mode_layout.addWidget(self.scale_btn)
        
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)
        
        # 添加视图设置组
        view_group = QGroupBox("视图设置")
        view_layout = QVBoxLayout()
        
        ortho_check = QCheckBox("正交投影")
        ortho_check.toggled.connect(self.toggle_ortho)
        view_layout.addWidget(ortho_check)
        
        view_group.setLayout(view_layout)
        layout.addWidget(view_group)
        
        # 添加伸缩项填充剩余空间
        layout.addStretch()
        
        # 设置主窗口
        self.setWidget(main_widget)
    
    def add_geometry(self):
        """根据下拉框选择添加不同类型的几何体，注意使用 Mujoco 半尺寸标准"""
        type_index = self.geo_type_combo.currentIndex()
        geo_type = [
            GeometryType.BOX, 
            GeometryType.SPHERE, 
            GeometryType.ELLIPSOID,
            GeometryType.CYLINDER,
            GeometryType.CAPSULE,
            GeometryType.PLANE
        ][type_index]
        
        # 为不同类型设置合适的默认尺寸（半长半宽半高）
        default_sizes = {
            GeometryType.BOX: (0.5, 0.5, 0.5),         # 半长半宽半高
            GeometryType.SPHERE: (0.5, 0.5, 0.5),      # 半径
            GeometryType.ELLIPSOID: (0.6, 0.4, 0.3),   # 三轴半径
            GeometryType.CYLINDER: (0.5, 0.5, 0.5),    # 半径, 半高
            GeometryType.CAPSULE: (0.5, 0.5, 0.5),     # 半径, 半高
            GeometryType.PLANE: (1.0, 1.0, 0.05)       # 半宽, 半长, 半厚
        }
        
        # 为不同类型设置默认名称
        type_names = {
            GeometryType.BOX: "立方体",
            GeometryType.SPHERE: "球体",
            GeometryType.ELLIPSOID: "椭球体",
            GeometryType.CYLINDER: "圆柱体",
            GeometryType.CAPSULE: "胶囊体",
            GeometryType.PLANE: "平面"
        }
        
        # 创建几何体
        count = sum(1 for geo in self.gl_widget.geometries if geo.type == geo_type)
        name = f"{type_names[geo_type]}_{count+1}"
        size = default_sizes[geo_type]
        
        # 创建几何体对象
        geo = Geometry(
            geo_type=geo_type,
            name=name,
            position=(0, 0, 0),
            size=size,
            rotation=(0, 0, 0)
        )
        
        # 添加到场景
        self.gl_widget.add_geometry(geo)
        
        # 选中新添加的几何体
        self.gl_widget.set_selection(geo)
        
        # 如果在观察模式，自动切换到平移模式
        if self.gl_widget.current_mode == OperationMode.MODE_OBSERVE:
            self.translate_btn.setChecked(True)
    
    def on_mode_changed(self, mode_id):
        """处理操作模式变更"""
        if self.sender().isChecked():  # 只在按钮被选中时处理
            self.gl_widget.set_operation_mode(mode_id)
    
    def toggle_ortho(self, checked):
        """切换正交/透视投影"""
        self.gl_widget.use_orthographic = checked
        self.gl_widget.update_camera_config()

    def update_mode_buttons(self, mode_id):
        """根据当前模式更新按钮状态"""
        # 阻断信号以避免循环触发
        with QSignalBlocker(self.observe_btn), QSignalBlocker(self.translate_btn), \
             QSignalBlocker(self.rotate_btn), QSignalBlocker(self.scale_btn):
            
            self.observe_btn.setChecked(mode_id == OperationMode.MODE_OBSERVE)
            self.translate_btn.setChecked(mode_id == OperationMode.MODE_TRANSLATE)
            self.rotate_btn.setChecked(mode_id == OperationMode.MODE_ROTATE)
            self.scale_btn.setChecked(mode_id == OperationMode.MODE_SCALE)

class PropertyPanel(QDockWidget):
    """显示和编辑选中几何体属性的面板"""
    def __init__(self, gl_widget):
        super().__init__("属性面板")
        self.gl_widget = gl_widget
        self.current_geo = None
        self._in_update = False
        
        # 创建主容器和布局
        self.widget = QWidget()
        self.main_layout = QVBoxLayout(self.widget)
        
        # 创建表单布局
        self.form_layout = QFormLayout()
        self.main_layout.addLayout(self.form_layout)
        
        # 初始化常用控件变量为空
        self.name_edit = None
        self.pos_spinners = []
        self.rot_spinners = []
        self.scale_spinners = []
        
        # 设置主控件
        self.setWidget(self.widget)
        
        # 监听场景中的选择变化
        self.gl_widget.selection_changed.connect(self.on_selection_changed)

    def on_selection_changed(self, geo):
        """当选择变更时更新面板内容"""
        # 先清除所有控件引用，避免访问已删除控件
        self.name_edit = None
        self.pos_spinners = []
        self.rot_spinners = []
        self.scale_spinners = []
        self.color_button = None  # 明确设置为 None
        self.roughness_slider = None
        self.metallic_slider = None
        self.visible_checkbox = None
        
        # 然后清除布局
        self.clear_layout(self.form_layout)
        
        if geo is None:
            self.current_geo = None
            return

        self.current_geo = geo
        
        # 添加名称字段
        self.name_edit = QLineEdit(geo.name)
        self.form_layout.addRow("名称:", self.name_edit)
        
        # 添加位置控件
        self.pos_spinners = []
        pos_layout = QHBoxLayout()
        for i, val in enumerate(geo.position):
            spinner = self._create_spinbox()
            spinner.setValue(val)
            self.pos_spinners.append(spinner)
            pos_layout.addWidget(spinner)
        self.form_layout.addRow("位置:", pos_layout)
        
        # 如果是几何体(不是组)，添加特有属性
        if hasattr(geo, 'type') and geo.type != "group":
            # 添加旋转控件
            self.rot_spinners = []
            rot_layout = QHBoxLayout()
            for i, val in enumerate(geo.rotation):
                spinner = self._create_spinbox()
                spinner.setValue(val)
                self.rot_spinners.append(spinner)
                rot_layout.addWidget(spinner)
            self.form_layout.addRow("旋转:", rot_layout)
            
            # 添加缩放控件
            self.scale_spinners = []
            scale_layout = QHBoxLayout()
            for i, val in enumerate(geo.size):
                spinner = self._create_spinbox(min_val=0.01, max_val=100)
                spinner.setValue(val)
                self.scale_spinners.append(spinner)
                scale_layout.addWidget(spinner)
            self.form_layout.addRow("缩放:", scale_layout)
            
            # 添加材质属性（如果存在）
            if hasattr(geo, 'material'):
                # 颜色选择按钮
                self.color_button = QPushButton()
                color = QColor.fromRgbF(*geo.material.color)
                self.color_button.setStyleSheet(f"background-color: {color.name()}")
                self.form_layout.addRow("颜色:", self.color_button)
                
                # 可能需要添加其他材质属性，如粗糙度、金属度等
                if hasattr(geo.material, 'roughness'):
                    self.roughness_slider = QSlider(Qt.Horizontal)
                    self.roughness_slider.setRange(0, 100)
                    self.roughness_slider.setValue(int(geo.material.roughness * 100))
                    self.form_layout.addRow("粗糙度:", self.roughness_slider)
                
                if hasattr(geo.material, 'metallic'):
                    self.metallic_slider = QSlider(Qt.Horizontal)
                    self.metallic_slider.setRange(0, 100)
                    self.metallic_slider.setValue(int(geo.material.metallic * 100))
                    self.form_layout.addRow("金属度:", self.metallic_slider)
        
        # 组特有属性
        if geo.type == "group":
            # 可以添加组特有的属性，如可见性等
            if hasattr(geo, 'visible'):
                self.visible_checkbox = QCheckBox()
                self.visible_checkbox.setChecked(geo.visible)
                self.form_layout.addRow("可见:", self.visible_checkbox)
        
        # 检查是否需要尝试连接信号
        has_controls = False
        
        # 只有在添加了控件后才连接信号
        if has_controls:
            self._connect_signals()

    def _create_spinbox(self, min_val=-999, max_val=999):
        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setSingleStep(0.1)
        spin.setMinimumWidth(100)
        return spin
        
    def _connect_signals(self):
        """安全信号连接方式"""
        # 名称编辑
        if hasattr(self, 'name_edit') and self.name_edit is not None:
            self.name_edit.editingFinished.connect(self._on_name_changed)
        
        # 数值控件统一处理
        if hasattr(self, 'pos_spinners') and self.pos_spinners:
            for spin in self.pos_spinners:
                if spin is not None:  # 添加额外检查
                    spin.valueChanged.connect(self._on_value_changed)
            
        if hasattr(self, 'rot_spinners') and self.rot_spinners:
            for spin in self.rot_spinners:
                if spin is not None:  # 添加额外检查
                    spin.valueChanged.connect(self._on_value_changed)
            
        if hasattr(self, 'scale_spinners') and self.scale_spinners:
            for spin in self.scale_spinners:
                if spin is not None:  # 添加额外检查
                    spin.valueChanged.connect(self._on_value_changed)
        
        # 颜色按钮
        if hasattr(self, 'color_button') and self.color_button is not None:
            self.color_button.clicked.connect(self._pick_color)
            
        # 可见性复选框
        if hasattr(self, 'visible_checkbox') and self.visible_checkbox is not None:
            self.visible_checkbox.toggled.connect(self._on_visibility_changed)
    
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
        if obj:
            # 选中对象（组或几何体）
            self.gl_widget.set_selection(obj)
            
            # 展开或折叠组
            if obj.type == "group":
                if item.isExpanded():
                    item.setExpanded(False)
                else:
                    item.setExpanded(True)
    
    def update_selection(self, obj):
        """更新树选择状态以匹配当前选中对象"""
        # 清除所有选择
        self.tree_widget.clearSelection()
        
        # 选中对应项
        if obj in self.obj_to_item:
            item = self.obj_to_item[obj]
            item.setSelected(True)
            
            # 确保项可见
            self.tree_widget.scrollToItem(item)
            
            # 展开父项以显示选中项
            parent_item = item.parent()
            while parent_item:
                parent_item.setExpanded(True)
                parent_item = parent_item.parent()
    
    def _show_context_menu(self, position):
        """显示右键菜单"""
        # 获取当前点击的项
        item = self.tree_widget.itemAt(position)
        if item:
            # 使用id(item)作为键来获取对应的对象
            obj = self.item_to_obj.get(id(item))
            
            menu = QMenu()
            
            # 根据对象类型添加不同菜单项
            if obj.type == "group":
                # 组特有菜单
                add_geo_menu = menu.addMenu("添加几何体")
                
                # 添加各种几何体类型
                for geo_type in [GeometryType.BOX, GeometryType.SPHERE, 
                                GeometryType.CYLINDER, GeometryType.CAPSULE,
                                GeometryType.PLANE, GeometryType.ELLIPSOID]:
                    action = add_geo_menu.addAction(geo_type.capitalize())
                    action.setData(("add_geo", obj, geo_type))
                
                # 添加子组
                add_group_action = menu.addAction("添加子组")
                add_group_action.setData(("add_group", obj))
            
            # 共有菜单项
            rename_action = menu.addAction("重命名")
            rename_action.setData(("rename", obj))
            
            delete_action = menu.addAction("删除")
            delete_action.setData(("delete", obj))
            
            # 显示菜单并处理选择
            selected_action = menu.exec_(self.tree_widget.mapToGlobal(position))
            if selected_action:
                action_data = selected_action.data()
                if action_data:
                    self._handle_context_action(action_data)
    
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
        """添加几何体到组"""
        # 创建新几何体
        new_geo = Geometry(
            geo_type=geo_type,
            name=f"New {geo_type.capitalize()}",
            position=(0, 0, 0)
        )
        
        # 添加到父组
        parent_group.add_child(new_geo)
        
        # 更新UI
        self.refresh()
        self.gl_widget.update()
    
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
                # 从父组中移除
                obj.parent.remove_child(obj)
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
        
        # 设置窗口大小
        self.resize(1200, 800)
    
    def create_menus(self):
        # 文件菜单
        file_menu = self.menuBar().addMenu("文件")
        
        open_action = QAction("打开", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

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

class XMLParser:
    @staticmethod
    def load(filename):
        try:
            tree = ET.parse(filename)
            root = tree.getroot()
            geometries = []
            
            # 解析XML结构
            for body in root.findall(".//body"):
                pos = list(map(float, body.get('pos', '0 0 0').split()))
                for geom in body.findall('geom'):
                    geo_type = geom.get('type')
                    size = list(map(float, geom.get('size', '1 1 1').split()))
                    
                    # 根据类型调整尺寸参数
                    if geo_type == 'sphere':
                        size = [size[0], size[0], size[0]]  # 球体使用相同的三个半径
                    elif geo_type == 'ellipsoid':
                        # 椭球体需要三个不同的半径
                        if len(size) < 3:
                            size.extend([size[0]] * (3 - len(size)))  # 补全缺少的尺寸
                    elif geo_type == 'capsule' or geo_type == 'cylinder':
                        # 半径和高度
                        if len(size) < 2:
                            size.append(1.0)  # 默认高度
                        size.append(0)  # 第三个参数设为0
                    
                    geometries.append(Geometry(
                        geo_type=geo_type,
                        name=body.get('name', 'Unnamed'),
                        position=pos,
                        size=size
                    ))
            return geometries
        except Exception as e:
            QMessageBox.critical(None, "错误", f"文件解析失败: {str(e)}")
            return []
    
    @staticmethod
    def save(filename, geometries):
        root = ET.Element('mujoco')
        worldbody = ET.SubElement(root, 'worldbody')
        
        for geo in geometries:
            body = ET.SubElement(worldbody, 'body', 
                               name=geo.name,
                               pos=" ".join(map(str, geo.position)))
            geom = ET.SubElement(body, 'geom',
                                type=geo.type,
                                size=" ".join(map(str, geo.size)),
                                rgba="0.8 0.5 0.2 1")
            
            # 添加旋转信息
            if any(geo.rotation):
                body.set('euler', " ".join(map(str, geo.rotation)))
        
        tree = ET.ElementTree(root)
        tree.write(filename, encoding='utf-8', xml_declaration=True)

class DraggableGeometryButton(QPushButton):
    """可拖拽的几何体创建按钮"""
    def __init__(self, geo_type, title, parent=None):
        super().__init__(title, parent)
        self.geo_type = geo_type
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        
    def mousePressEvent(self, event):
        """开始拖拽"""
        if event.button() == Qt.LeftButton:
            # 创建拖拽对象
            drag = QDrag(self)
            mime_data = QMimeData()
            
            # 存储几何体类型
            mime_data.setText(self.geo_type)
            drag.setMimeData(mime_data)
            
            # 创建拖拽时的预览图像
            pixmap = QPixmap(self.size())
            self.render(pixmap)
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.pos())
            
            # 开始拖拽
            drag.exec_(Qt.CopyAction)
        else:
            super().mousePressEvent(event)



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