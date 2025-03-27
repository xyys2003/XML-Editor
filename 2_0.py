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
        self.selected_geos = []  # 新增：存储多个选中对象
        self.selected_geo = None  # 保留现有的单选，用于变换操作
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
        """重写的绘制函数，考虑父级变换"""
        # 清除缓冲区
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        # 设置相机
        eye_pos = self.camera_config['position']
        gluLookAt(*eye_pos, *self._camera_target, 0, 0, 1)
        
        # 1. 绘制基础场景元素
        self.draw_infinite_grid()
        self.draw_infinite_axes()
        
        # 2. 绘制所有物体（包括选中物体的特殊效果）
        self._draw_geometries_recursive(self.geometries)
        
        # 3. 如果有选中物体，绘制变换控件
        if self.selected_geo and self.current_mode != OperationMode.MODE_OBSERVE:
            glDisable(GL_BLEND)
            self.draw_gizmo()
        
        # 4. 绘制拖放预览
        if hasattr(self, 'drag_preview') and self.drag_preview.get('active') and self.drag_preview.get('position') is not None:
            self._draw_drag_preview()

    def _draw_geometries_recursive(self, geometries, skip_selected=True):
        """递归绘制几何体和组
        Args:
            geometries: 要绘制的几何体/组列表
            skip_selected: 是否使用选中对象的特殊绘制效果
        """
        for geo in geometries:
            # 如果是组，递归绘制其子对象
            if isinstance(geo, GeometryGroup):
                self._draw_geometries_recursive(geo.children, skip_selected)
                continue
            
            # 处理几何体的绘制
            is_selected = (geo == self.selected_geo)
            
            # 如果是选中的对象且需要特殊处理
            if is_selected and skip_selected:
                if geo.parent:
                    self.draw_geometry(geo, parent_transform=geo.parent.transform_matrix, alpha=0.75)
                else:
                    self.draw_geometry(geo)
            # 如果是非选中对象或不需要特殊处理
            else:
                if geo.parent:
                    self.draw_geometry(geo, parent_transform=geo.parent.transform_matrix)
                else:
                    self.draw_geometry(geo)

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
        # if hasattr(geo, 'selected') and geo.selected:
        #     self.draw_outline(geo)
        
        glPopMatrix()

    def draw_gizmo(self):
        """根据当前选择和操作模式绘制变换控件"""
        if not self.selected_geo:
            return
        
        try:
            # 获取对象的世界坐标位置
            if self.selected_geo.type == "group":
                world_position = self.selected_geo.get_world_position()
            else:
                world_position = self.selected_geo.position.copy()
            
            # 保存当前材质和光照状态
            glPushAttrib(GL_LIGHTING_BIT | GL_CURRENT_BIT | GL_LINE_BIT | GL_DEPTH_BUFFER_BIT)
            
            # 根据当前操作模式绘制不同的控件
            if self.current_mode == OperationMode.MODE_TRANSLATE or self.current_mode == OperationMode.MODE_SCALE:
                # 平移和缩放模式都使用浮动坐标系
                self.draw_floating_gizmo(self.selected_geo)
            elif self.current_mode == OperationMode.MODE_ROTATE:
                # 旋转模式使用旋转控件
                self._draw_rotation_gizmo(world_position)
            
            # 恢复状态
            glPopAttrib()
        except Exception as e:
            print(f"绘制控件出错: {str(e)}")

    def _draw_scale_gizmo(self, position):
        """绘制缩放控件"""
        # 控件尺寸
        axis_length = 1.5   # 坐标轴长度
        axis_radius = 0.03  # 坐标轴半径
        box_size = 0.1      # 缩放手柄大小
        
        # 禁用深度测试和光照
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        
        # 绘制X轴（红色）
        if self.active_axis == 0:
            glColor3f(1.0, 1.0, 0.0)  # 高亮为黄色
        else:
            glColor3f(1.0, 0.0, 0.0)  # 红色
        
        # 绘制X轴圆柱体
        self._draw_axis_cylinder(
            position[0], position[1], position[2],
            position[0] + axis_length, position[1], position[2],
            axis_radius
        )
        
        # 绘制X轴手柄（立方体）
        glPushMatrix()
        glTranslatef(position[0] + axis_length, position[1], position[2])
        self._draw_cube(box_size)
        glPopMatrix()
        
        # 绘制Y轴（绿色）
        if self.active_axis == 1:
            glColor3f(1.0, 1.0, 0.0)  # 高亮为黄色
        else:
            glColor3f(0.0, 1.0, 0.0)  # 绿色
        
        # 绘制Y轴圆柱体
        self._draw_axis_cylinder(
            position[0], position[1], position[2],
            position[0], position[1] + axis_length, position[2],
            axis_radius
        )
        
        # 绘制Y轴手柄
        glPushMatrix()
        glTranslatef(position[0], position[1] + axis_length, position[2])
        self._draw_cube(box_size)
        glPopMatrix()
        
        # 绘制Z轴（蓝色）
        if self.active_axis == 2:
            glColor3f(1.0, 1.0, 0.0)  # 高亮为黄色
        else:
            glColor3f(0.0, 0.0, 1.0)  # 蓝色
        
        # 绘制Z轴圆柱体
        self._draw_axis_cylinder(
            position[0], position[1], position[2],
            position[0], position[1], position[2] + axis_length,
            axis_radius
        )
        
        # 绘制Z轴手柄
        glPushMatrix()
        glTranslatef(position[0], position[1], position[2] + axis_length)
        self._draw_cube(box_size)
        glPopMatrix()
        
        # 绘制中心手柄（均匀缩放）
        if self.active_axis == 3:
            glColor3f(1.0, 1.0, 0.0)  # 高亮为黄色
        else:
            glColor3f(1.0, 1.0, 1.0)  # 白色
        
        # 绘制中心缩放手柄
        glPushMatrix()
        glTranslatef(position[0], position[1], position[2])
        self._draw_cube(box_size * 1.2)  # 中心手柄稍大一些
        glPopMatrix()
        
        # 恢复深度测试和光照
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

    def _draw_cube(self, size):
        """绘制一个立方体
        
        Args:
            size: 立方体边长的一半
        """
        glBegin(GL_QUADS)
        
        # 前面
        glVertex3f(-size, -size, size)
        glVertex3f(size, -size, size)
        glVertex3f(size, size, size)
        glVertex3f(-size, size, size)
        
        # 后面
        glVertex3f(-size, -size, -size)
        glVertex3f(-size, size, -size)
        glVertex3f(size, size, -size)
        glVertex3f(size, -size, -size)
        
        # 上面
        glVertex3f(-size, size, -size)
        glVertex3f(-size, size, size)
        glVertex3f(size, size, size)
        glVertex3f(size, size, -size)
        
        # 下面
        glVertex3f(-size, -size, -size)
        glVertex3f(size, -size, -size)
        glVertex3f(size, -size, size)
        glVertex3f(-size, -size, size)
        
        # 右面
        glVertex3f(size, -size, -size)
        glVertex3f(size, size, -size)
        glVertex3f(size, size, size)
        glVertex3f(size, -size, size)
        
        # 左面
        glVertex3f(-size, -size, -size)
        glVertex3f(-size, -size, size)
        glVertex3f(-size, size, size)
        glVertex3f(-size, size, -size)
        
        glEnd()

    def _draw_translation_gizmo(self, position):
        """绘制平移控件"""
        # 只有在平移模式下才绘制
        if self.current_mode != OperationMode.MODE_TRANSLATE:
            return
        
        # 控件尺寸
        axis_length = 1.5  # 坐标轴长度
        axis_width = 2.0   # 坐标轴线宽
        cone_height = 0.2  # 箭头锥体高度
        cone_radius = 0.05 # 箭头锥体半径
        
        # 禁用深度测试和光照
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        
        # 设置线宽
        glLineWidth(axis_width)
        
        # 绘制X轴（红色）
        if self.active_axis == 0:
            glColor3f(1.0, 1.0, 0.0)  # 高亮为黄色
        else:
            glColor3f(1.0, 0.0, 0.0)  # 红色
        
        # 绘制X轴线
        glBegin(GL_LINES)
        glVertex3f(position[0], position[1], position[2])
        glVertex3f(position[0] + axis_length, position[1], position[2])
        glEnd()
        
        # 绘制X轴箭头
        self._draw_cone(
            position[0] + axis_length, position[1], position[2],
            position[0] + axis_length + cone_height, position[1], position[2],
            cone_radius
        )
        
        # 绘制Y轴（绿色）
        if self.active_axis == 1:
            glColor3f(1.0, 1.0, 0.0)  # 高亮为黄色
        else:
            glColor3f(0.0, 1.0, 0.0)  # 绿色
        
        # 绘制Y轴线
        glBegin(GL_LINES)
        glVertex3f(position[0], position[1], position[2])
        glVertex3f(position[0], position[1] + axis_length, position[2])
        glEnd()
        
        # 绘制Y轴箭头
        self._draw_cone(
            position[0], position[1] + axis_length, position[2],
            position[0], position[1] + axis_length + cone_height, position[2],
            cone_radius
        )
        
        # 绘制Z轴（蓝色）
        if self.active_axis == 2:
            glColor3f(1.0, 1.0, 0.0)  # 高亮为黄色
        else:
            glColor3f(0.0, 0.0, 1.0)  # 蓝色
        
        # 绘制Z轴线
        glBegin(GL_LINES)
        glVertex3f(position[0], position[1], position[2])
        glVertex3f(position[0], position[1], position[2] + axis_length)
        glEnd()
        
        # 绘制Z轴箭头
        self._draw_cone(
            position[0], position[1], position[2] + axis_length,
            position[0], position[1], position[2] + axis_length + cone_height,
            cone_radius
        )
        
        # 恢复深度测试和光照
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

    def _draw_cone(self, x1, y1, z1, x2, y2, z2, radius):
        """绘制圆锥"""
        # 计算圆锥的方向向量
        dx = x2 - x1
        dy = y2 - y1
        dz = z2 - z1
        length = np.sqrt(dx*dx + dy*dy + dz*dz)
        
        # 避免除以零
        if length < 1e-6:
            return
        
        # 单位化方向向量
        dx /= length
        dy /= length
        dz /= length
        
        # 找到与方向向量垂直的轴
        ax, ay, az = 0, 0, 0
        if abs(dx) < abs(dy):
            ax = 1.0
        else:
            ay = 1.0
        
        # 计算垂直于方向的两个基向量
        bx = ay*dz - az*dy
        by = az*dx - ax*dz
        bz = ax*dy - ay*dx
        
        # 单位化第一个基向量
        b_length = np.sqrt(bx*bx + by*by + bz*bz)
        if b_length < 1e-6:
            return
        
        bx /= b_length
        by /= b_length
        bz /= b_length
        
        # 计算第二个基向量（叉积）
        cx = dy*bz - dz*by
        cy = dz*bx - dx*bz
        cz = dx*by - dy*bx
        
        # 绘制圆锥底部的圆
        slices = 16
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(x1, y1, z1)  # 顶点
        
        for i in range(slices+1):
            angle = 2.0 * np.pi * i / slices
            px = x1 + radius * (bx * np.cos(angle) + cx * np.sin(angle))
            py = y1 + radius * (by * np.cos(angle) + cy * np.sin(angle))
            pz = z1 + radius * (bz * np.cos(angle) + cz * np.sin(angle))
            glVertex3f(px, py, pz)
        
        glEnd()
        
        # 绘制圆锥侧面
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(x2, y2, z2)  # 圆锥顶点
        
        for i in range(slices+1):
            angle = 2.0 * np.pi * i / slices
            px = x1 + radius * (bx * np.cos(angle) + cx * np.sin(angle))
            py = y1 + radius * (by * np.cos(angle) + cy * np.sin(angle))
            pz = z1 + radius * (bz * np.cos(angle) + cz * np.sin(angle))
            glVertex3f(px, py, pz)
        
        glEnd()

    def detect_axis(self, mouse_pos):
        """检测鼠标与哪个轴相交"""
        if not self.selected_geo:
            return -1
            
        try:
            if self.current_mode in [OperationMode.MODE_TRANSLATE, OperationMode.MODE_SCALE]:
                # 平移和缩放模式都使用浮动坐标系的轴检测
                return self.detect_floating_axis(mouse_pos)
            elif self.current_mode == OperationMode.MODE_ROTATE:
                # 旋转模式使用旋转轴检测
                return self._detect_rotation_axis(mouse_pos, self.selected_geo.position)
                
            return -1
        except Exception as e:
            print(f"轴检测出错: {str(e)}")
            return -1

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
        if self.left_button_pressed and self.dragging and self.active_axis is not None:
            # 统一使用handle_axis_drag处理所有轴拖动
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
        """更新选中状态"""
        # 检查是否按住了Ctrl键
        ctrl_pressed = QApplication.keyboardModifiers() & Qt.ControlModifier
        
        if not ctrl_pressed:
            # 没有按Ctrl，清除之前的选择，进行单选
            self.selected_geos.clear()
            self.selected_geo = geo
            if geo:
                self.selected_geos.append(geo)
        else:
            # 按住Ctrl进行多选
            if geo:
                if geo in self.selected_geos:
                    # 如果对象已经被选中，则取消选择
                    print(f"取消选中对象: {geo.name}")
                    self.selected_geos.remove(geo)
                    # 更新selected_geo为最后一个选中的对象
                    self.selected_geo = self.selected_geos[-1] if self.selected_geos else None
                else:
                    print(f"添加新的选中对象: {geo.name}")
                    # 添加新的选中对象
                    self.selected_geos.append(geo)
                    self.selected_geo = geo  # 最后选中的对象用于变换操作
        
        # 发送选择改变信号
        self.selection_changed.emit(self.selected_geo)
        self.update()

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
        """绘制无限网格"""
        # 保存当前颜色
        current_color = glGetFloatv(GL_CURRENT_COLOR)
        
        # 设置网格线属性
        glLineWidth(1.0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        # 绘制主网格
        center_x = 0
        center_z = 0
        main_interval = 1.0
        main_extent = 50.0
        
        # 主网格线（较暗）
        glColor4f(0.5, 0.5, 0.5, 0.3)
        self._draw_grid_lines(center_x, center_z, main_interval, main_extent)
        
        # 次网格线（更暗）
        glColor4f(0.3, 0.3, 0.3, 0.15)
        self._draw_grid_lines(center_x, center_z, main_interval/5, main_extent)
        
        # 恢复原始颜色
        glColor4fv(current_color)

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

    def add_geometry(self, geo, parent=None):
        """添加几何体到场景，考虑父级"""
        if parent:
            # 添加到父组
            parent.add_child(geo)
            geo.parent = parent
        else:
            # 添加到根级
            self.geometries.append(geo)
        
        # 如果是组，确保更新其变换矩阵
        if geo.type == "group":
            if hasattr(geo, '_update_transform'):
                geo._update_transform()
        
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
        """检测鼠标与哪个轴相交"""
        if not self.selected_geo:
            return -1
            
        try:
            if self.current_mode in [OperationMode.MODE_TRANSLATE, OperationMode.MODE_SCALE]:
                # 平移和缩放模式都使用浮动坐标系的轴检测
                return self.detect_floating_axis(mouse_pos)
            elif self.current_mode == OperationMode.MODE_ROTATE:
                # 旋转模式使用旋转轴检测
                return self._detect_rotation_axis(mouse_pos, self.selected_geo.position)
                
            return -1
        except Exception as e:
            print(f"轴检测出错: {str(e)}")
            return -1

    def handle_axis_drag(self, dx, dy):
        """统一处理轴向拖动"""
        if not hasattr(self, 'active_axis') or not self.selected_geo:
            return
            
        # 根据当前操作模式调用相应的处理函数
        if self.current_mode == OperationMode.MODE_TRANSLATE:
            self._handle_translate_drag(dx, dy)
        elif self.current_mode == OperationMode.MODE_ROTATE:
            # 根据活动轴确定旋转方向
            rotation_amount = dx * 0.5  # 可以调整这个系数来控制旋转速度
            
            # 根据选中的轴更新相应的旋转角度
            if self.active_axis == 'x':
                self.selected_geo.rotation[0] += rotation_amount
            elif self.active_axis == 'y':
                self.selected_geo.rotation[1] += rotation_amount
            elif self.active_axis == 'z':
                self.selected_geo.rotation[2] += rotation_amount
            
            # 更新变换
            if hasattr(self.selected_geo, '_update_transform'):
                self.selected_geo._update_transform()
            
            # 如果是组，更新所有子对象
            if self.selected_geo.type == "group":
                self.update_group_transforms_recursive(self.selected_geo)
                
        elif self.current_mode == OperationMode.MODE_SCALE:
            self._handle_scale_drag(dx, dy)
            
        self.update()

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
        """处理缩放拖拽，将鼠标拖动转换为物体缩放"""
        if not self.selected_geo or self.active_axis == -1:
            return
        
        try:
            # 获取鼠标移动在屏幕中的位置变化
            screen_dx = dx
            screen_dy = dy
            
            # 获取当前视图方向
            view_dir = self._camera_target - self.camera_config['position']
            view_dir = view_dir / np.linalg.norm(view_dir)
            
            # 定义三个坐标轴方向向量
            axis_vectors = [
                np.array([1, 0, 0]),  # X轴
                np.array([0, 1, 0]),  # Y轴
                np.array([0, 0, 1])   # Z轴
            ]
            
            # 计算视图方向与各坐标轴的点积，确定拖动方向
            if self.active_axis < 3:  # 单轴缩放
                axis_vector = axis_vectors[self.active_axis]
                
                # 计算视图与轴之间的点积，决定正负方向
                view_dot = np.dot(view_dir, axis_vector)
                
                # 计算有效拖动量：水平拖动(dx)更符合直觉
                # 如果轴与视图接近垂直，使用垂直拖动(dy)
                if abs(view_dot) < 0.3:
                    drag_amount = -dy * 0.01  # 垂直拖动，上移增大
                else:
                    # 确定水平拖动方向（右移增大还是左移增大）
                    drag_amount = dx * 0.01 * (1 if view_dot < 0 else -1)
                
                # 获取当前尺寸
                current_size = list(self.selected_geo.size)
                
                # 应用缩放
                current_size[self.active_axis] += drag_amount
                
                # 确保尺寸不会太小
                current_size[self.active_axis] = max(0.1, current_size[self.active_axis])
                
                # 应用新的尺寸
                self.selected_geo.size = current_size
            
            elif self.active_axis == 3:  # 均匀缩放（中心控件）
                # 对于均匀缩放，使用水平和垂直拖动的平均值
                drag_amount = (dx + dy) * 0.005
                
                # 获取当前尺寸
                current_size = list(self.selected_geo.size)
                
                # 均匀应用缩放
                for i in range(3):
                    current_size[i] += drag_amount
                    current_size[i] = max(0.1, current_size[i])
                
                # 应用新的尺寸
                self.selected_geo.size = current_size
            
            # 如果是组，确保更新子对象的变换
            if self.selected_geo.type == "group":
                if hasattr(self.selected_geo, '_update_transform'):
                    self.selected_geo._update_transform()
                if hasattr(self.selected_geo, '_update_children_transforms'):
                    self.selected_geo._update_children_transforms()
        
        except Exception as e:
            print(f"缩放拖拽出错: {str(e)}")
            import traceback
            traceback.print_exc()

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
    
    
    def draw_outline(self, geo, parent_transform=None):
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
        """检测鼠标与哪个轴相交"""
        if not self.selected_geo:
            return -1
            
        try:
            if self.current_mode in [OperationMode.MODE_TRANSLATE, OperationMode.MODE_SCALE]:
                # 平移和缩放模式都使用浮动坐标系的轴检测
                return self.detect_floating_axis(mouse_pos)
            elif self.current_mode == OperationMode.MODE_ROTATE:
                # 旋转模式使用旋转轴检测
                return self._detect_rotation_axis(mouse_pos, self.selected_geo.position)
                
            return -1
        except Exception as e:
            print(f"轴检测出错: {str(e)}")
            return -1

    def handle_axis_drag(self, dx, dy):
        """统一处理轴向拖动"""
        if not hasattr(self, 'active_axis') or not self.selected_geo:
            return
            
        # 根据当前操作模式调用相应的处理函数
        if self.current_mode == OperationMode.MODE_TRANSLATE:
            self._handle_translate_drag(dx, dy)
        elif self.current_mode == OperationMode.MODE_ROTATE:
            # 根据活动轴确定旋转方向
            rotation_amount = dx * 0.5  # 可以调整这个系数来控制旋转速度
            
            # 根据选中的轴更新相应的旋转角度
            if self.active_axis == 'x':
                self.selected_geo.rotation[0] += rotation_amount
            elif self.active_axis == 'y':
                self.selected_geo.rotation[1] += rotation_amount
            elif self.active_axis == 'z':
                self.selected_geo.rotation[2] += rotation_amount
            
            # 更新变换
            if hasattr(self.selected_geo, '_update_transform'):
                self.selected_geo._update_transform()
            
            # 如果是组，更新所有子对象
            if self.selected_geo.type == "group":
                self.update_group_transforms_recursive(self.selected_geo)
                
        elif self.current_mode == OperationMode.MODE_SCALE:
            self._handle_scale_drag(dx, dy)
            
        self.update()

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
        """处理缩放拖拽，将鼠标拖动转换为物体缩放"""
        if not self.selected_geo or self.active_axis == -1:
            return
        
        try:
            # 获取鼠标移动在屏幕中的位置变化
            screen_dx = dx
            screen_dy = dy
            
            # 获取当前视图方向
            view_dir = self._camera_target - self.camera_config['position']
            view_dir = view_dir / np.linalg.norm(view_dir)
            
            # 定义三个坐标轴方向向量
            axis_vectors = [
                np.array([1, 0, 0]),  # X轴
                np.array([0, 1, 0]),  # Y轴
                np.array([0, 0, 1])   # Z轴
            ]
            
            # 计算视图方向与各坐标轴的点积，确定拖动方向
            if self.active_axis < 3:  # 单轴缩放
                axis_vector = axis_vectors[self.active_axis]
                
                # 计算视图与轴之间的点积，决定正负方向
                view_dot = np.dot(view_dir, axis_vector)
                
                # 计算有效拖动量：水平拖动(dx)更符合直觉
                # 如果轴与视图接近垂直，使用垂直拖动(dy)
                if abs(view_dot) < 0.3:
                    drag_amount = -dy * 0.01  # 垂直拖动，上移增大
                else:
                    # 确定水平拖动方向（右移增大还是左移增大）
                    drag_amount = dx * 0.01 * (1 if view_dot < 0 else -1)
                
                # 获取当前尺寸
                current_size = list(self.selected_geo.size)
                
                # 应用缩放
                current_size[self.active_axis] += drag_amount
                
                # 确保尺寸不会太小
                current_size[self.active_axis] = max(0.1, current_size[self.active_axis])
                
                # 应用新的尺寸
                self.selected_geo.size = current_size
            
            elif self.active_axis == 3:  # 均匀缩放（中心控件）
                # 对于均匀缩放，使用水平和垂直拖动的平均值
                drag_amount = (dx + dy) * 0.005
                
                # 获取当前尺寸
                current_size = list(self.selected_geo.size)
                
                # 均匀应用缩放
                for i in range(3):
                    current_size[i] += drag_amount
                    current_size[i] = max(0.1, current_size[i])
                
                # 应用新的尺寸
                self.selected_geo.size = current_size
            
            # 如果是组，确保更新子对象的变换
            if self.selected_geo.type == "group":
                if hasattr(self.selected_geo, '_update_transform'):
                    self.selected_geo._update_transform()
                if hasattr(self.selected_geo, '_update_children_transforms'):
                    self.selected_geo._update_children_transforms()
        
        except Exception as e:
            print(f"缩放拖拽出错: {str(e)}")
            import traceback
            traceback.print_exc()

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
    
    
    def draw_outline(self, geo, parent_transform=None):
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
        axis_length = max(2.5, obj_size * 0.8)
        axis_thickness = axis_length * 0.05  # 轴的粗细
        
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
        """计算射线与圆柱体的交点，返回相交距离"""
        # 圆柱体方向向量
        cylinder_direction = cylinder_end - cylinder_start
        cylinder_length = np.linalg.norm(cylinder_direction)
        
        if cylinder_length < 1e-6:
            return None  # 圆柱体长度太小，视为无效
        
        # 归一化圆柱体方向
        cylinder_direction = cylinder_direction / cylinder_length
        
        # 计算射线与圆柱体轴线之间的最近点
        w = ray_origin - cylinder_start
        a = np.dot(ray_direction, ray_direction) - np.dot(ray_direction, cylinder_direction)**2
        b = np.dot(ray_direction, w) - np.dot(ray_direction, cylinder_direction) * np.dot(w, cylinder_direction)
        c = np.dot(w, w) - np.dot(w, cylinder_direction)**2 - radius**2
        
        if abs(a) < 1e-6:
            return None  # 射线与圆柱体平行或者几乎平行
        
        # 解二次方程
        discriminant = b*b - a*c
        
        if discriminant < 0:
            return None  # 没有实数解，射线未击中圆柱体
        
        # 计算最近的交点
        t = (-b - np.sqrt(discriminant)) / a
        
        if t < 0:
            # 如果最近的交点在射线起点后面，检查另一个交点
            t = (-b + np.sqrt(discriminant)) / a
            if t < 0:
                return None  # 两个交点都在射线起点后面
        
        # 计算交点的位置
        hit_point = ray_origin + t * ray_direction
        
        # 检查交点是否在圆柱体长度范围内
        v = hit_point - cylinder_start
        projection = np.dot(v, cylinder_direction)
        
        if projection < 0 or projection > cylinder_length:
            return None  # 交点在圆柱体外部
        
        # 返回交点距离
        return t

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

    def update_group_transforms_recursive(self, group):
        """递归更新组及其所有子组的变换矩阵"""
        # 首先更新当前组的变换矩阵
        # 这里假设已经有了_update_transform方法
        if hasattr(group, '_update_transform'):
            group._update_transform()
        
        # 递归更新所有子组
        for child in group.children:
            if child.type == "group":
                self.update_group_transforms_recursive(child)
            # 对于几何体不需要处理，因为几何体的变换会在绘制时考虑

    def update_transforms_recursive(self, obj):
        """递归更新对象及其所有子对象的变换矩阵
        
        Args:
            obj: 需要更新变换的对象(几何体或组)
        """
        if obj.type == "group":
            # 更新组自身的变换矩阵
            # 创建当前组的变换矩阵
            transform = np.identity(4)
            
            # 平移
            translation = np.array([
                [1, 0, 0, obj.position[0]],
                [0, 1, 0, obj.position[1]],
                [0, 0, 1, obj.position[2]],
                [0, 0, 0, 1]
            ])
            transform = np.dot(translation, transform)
            
            # 旋转
            for i, angle in enumerate(obj.rotation):
                # 为X、Y、Z轴创建旋转矩阵
                rotation = np.identity(4)
                angle_rad = np.radians(angle)
                c = np.cos(angle_rad)
                s = np.sin(angle_rad)
                
                if i == 0:  # X轴旋转
                    rotation[1:3, 1:3] = [[c, -s], [s, c]]
                elif i == 1:  # Y轴旋转
                    rotation[0, 0] = c
                    rotation[0, 2] = s
                    rotation[2, 0] = -s
                    rotation[2, 2] = c
                elif i == 2:  # Z轴旋转
                    rotation[0:2, 0:2] = [[c, -s], [s, c]]
                
                transform = np.dot(rotation, transform)
            
            # 如果有父组，需要考虑父组的变换
            if obj.parent is not None:
                parent_transform = obj.parent.transform_matrix
                transform = np.dot(parent_transform, transform)
            
            # 保存计算后的变换矩阵
            obj.transform_matrix = transform
            
            # 递归处理所有子对象
            for child in obj.children:
                self.update_transforms_recursive(child)
        else:
            # 处理非组对象(几何体)
            # 几何体只需要确保其父级变换已更新
            # 实际绘制时会考虑父级变换
            if hasattr(obj, "_update_transform"):
                obj._update_transform()  # 更新自身的局部变换

    def _draw_rotation_gizmo(self, position):
        """绘制不与物体重合的旋转控件"""
        if not self.selected_geo:
            return
            
        # 计算物体的世界坐标位置和尺寸
        obj_pos = self.selected_geo.position
        obj_size = np.max(self.selected_geo.size)
        
        # 确定控件的位置 - 距离物体一定距离
        camera_pos = self.camera_config['position']
        camera_dir = self._camera_target - camera_pos
        
        # 计算相机到物体的方向
        to_obj_dir = obj_pos - camera_pos
        to_obj_dist = np.linalg.norm(to_obj_dir)
        
        # 更新相机向量
        self.update_camera_vectors()
        
        # 使用相机的右向量确定控件位置
        offset_distance = max(obj_size * 2.5, 1.0)
        gizmo_pos = obj_pos + self.camera_right * offset_distance + np.array([0, 0, offset_distance * 0.5])
        
        if self.selected_geo.type == GeometryType.PLANE:
            gizmo_pos = obj_pos + np.array([0, 0, offset_distance])
        
        # 控件参数
        axis_length = max(2.5, obj_size * 0.8)
        axis_thickness = axis_length * 0.05
        
        # 保存当前状态
        current_color = glGetFloatv(GL_CURRENT_COLOR)
        
        try:
            glDisable(GL_DEPTH_TEST)
            glDisable(GL_LIGHTING)
            
            # 绘制原点球
            glPushMatrix()
            glTranslatef(*gizmo_pos)
            
            glColor3f(0.8, 0.8, 0.8)
            glutSolidSphere(axis_thickness * 1.5, 12, 12)
            
            # 存储几何信息用于检测
            self.rotation_gizmo_geometries = []
            
            # X轴旋转控件（红色）
            glColor3f(1.0, 0.0, 0.0)
            self._draw_axis_cylinder(
                0, -axis_length/2, 0,  # 起点
                0, axis_length/2, 0,   # 终点
                axis_thickness
            )
            x_axis_geo = Geometry(
                geo_type=GeometryType.CYLINDER,
                name="rotation_x_axis",
                position=gizmo_pos,
                size=[axis_thickness, axis_length/2, 0],
                rotation=[0, 0, 0]
            )
            x_axis_geo.material.color = [1.0, 0.0, 0.0, 1.0]
            self.rotation_gizmo_geometries.append(('x', x_axis_geo))
            
            # Y轴旋转控件（绿色）
            glColor3f(0.0, 1.0, 0.0)
            self._draw_axis_cylinder(
                -axis_length/2, 0, 0,  # 起点
                axis_length/2, 0, 0,   # 终点
                axis_thickness
            )
            y_axis_geo = Geometry(
                geo_type=GeometryType.CYLINDER,
                name="rotation_y_axis",
                position=gizmo_pos,
                size=[axis_thickness, axis_length/2, 0],
                rotation=[0, 90, 0]
            )
            y_axis_geo.material.color = [0.0, 1.0, 0.0, 1.0]
            self.rotation_gizmo_geometries.append(('y', y_axis_geo))
            
            # Z轴旋转控件（蓝色）
            glColor3f(0.0, 0.0, 1.0)
            self._draw_axis_cylinder(
                0, 0, -axis_length/2,  # 起点
                0, 0, axis_length/2,   # 终点
                axis_thickness
            )
            z_axis_geo = Geometry(
                geo_type=GeometryType.CYLINDER,
                name="rotation_z_axis",
                position=gizmo_pos,
                size=[axis_thickness, axis_length/2, 0],
                rotation=[90, 0, 0]
            )
            z_axis_geo.material.color = [0.0, 0.0, 1.0, 1.0]
            self.rotation_gizmo_geometries.append(('z', z_axis_geo))
            
            # 如果有活动轴，绘制高亮
            if hasattr(self, 'active_axis'):
                glColor3f(1, 1, 0)  # 黄色高亮
                if self.active_axis == 'x':
                    self._draw_axis_cylinder(
                        0, -axis_length/2, 0,
                        0, axis_length/2, 0,
                        axis_thickness * 1.2
                    )
                elif self.active_axis == 'y':
                    self._draw_axis_cylinder(
                        -axis_length/2, 0, 0,
                        axis_length/2, 0, 0,
                        axis_thickness * 1.2
                    )
                elif self.active_axis == 'z':
                    self._draw_axis_cylinder(
                        0, 0, -axis_length/2,
                        0, 0, axis_length/2,
                        axis_thickness * 1.2
                    )
                
        finally:
            # 恢复状态
            glPopMatrix()
            glEnable(GL_LIGHTING)
            glEnable(GL_DEPTH_TEST)
            glColor4fv(current_color)
            
        # 存储控件位置信息供检测使用
        self.rotation_gizmo_pos = gizmo_pos

    def _detect_rotation_axis(self, mouse_pos, position):
        """检测旋转轴的点击"""
        ray_origin, ray_direction = self._get_mouse_ray(mouse_pos)
        
        # 控件参数
        axis_length = 1.2
        axis_radius = 0.03
        
        # 定义三个旋转轴的圆柱体
        cylinders = [
            # X轴旋转控件（垂直于X轴）
            {
                'start': position + np.array([0, -axis_length/2, 0]),
                'end': position + np.array([0, axis_length/2, 0]),
                'axis': 'x'
            },
            # Y轴旋转控件
            {
                'start': position + np.array([-axis_length/2, 0, 0]),
                'end': position + np.array([axis_length/2, 0, 0]),
                'axis': 'y'
            },
            # Z轴旋转控件（需要考虑90度旋转）
            {
                'start': position + np.array([0, 0, -axis_length/2]),
                'end': position + np.array([0, 0, axis_length/2]),
                'axis': 'z'
            }
        ]
        
        # 检测与每个圆柱体的相交
        min_distance = float('inf')
        selected_axis = None
        
        for cylinder in cylinders:
            result = self._ray_cylinder_intersection(
                ray_origin, 
                ray_direction,
                cylinder['start'],
                cylinder['end'],
                axis_radius
            )
            
            if result is not None:
                distance = result[3] if isinstance(result, np.ndarray) else result
                
                if distance > 0 and distance < min_distance:
                    min_distance = distance
                    selected_axis = cylinder['axis']
    
        return selected_axis

    def _handle_rotate_drag(self, dx, dy):
        """处理旋转拖动"""
        if not hasattr(self, 'active_axis') or not self.selected_geo:
            return
            
        # 根据活动轴确定旋转方向
        rotation_amount = dx * 0.5  # 可以调整这个系数来控制旋转速度
        
        if self.active_axis == 'x':
            self.selected_geo.rotation[0] += rotation_amount
        elif self.active_axis == 'y':
            self.selected_geo.rotation[1] += rotation_amount
        elif self.active_axis == 'z':
            self.selected_geo.rotation[2] += rotation_amount
        
        # 更新变换
        if hasattr(self.selected_geo, '_update_transform'):
            self.selected_geo._update_transform()
        
        # 如果是组，更新所有子对象
        if self.selected_geo.type == "group":
            self.update_group_transforms_recursive(self.selected_geo)
        
        self.update()

    def _draw_circle(self, radius, segments, line_width=10.0):
        """绘制一个圆形
        
        Args:
            radius: 圆的半径
            segments: 圆的细分段数
            line_width: 线宽
        """
        glLineWidth(line_width)
        glBegin(GL_LINE_LOOP)
        for i in range(segments):
            angle = 2.0 * np.pi * i / segments
            x = radius * np.cos(angle)
            y = radius * np.sin(angle)
            glVertex3f(x, y, 0)
        glEnd()

    def detect_axis(self, mouse_pos):
        """检测鼠标与哪个轴相交"""
        if not self.selected_geo:
            return -1
            
        try:
            if self.current_mode in [OperationMode.MODE_TRANSLATE, OperationMode.MODE_SCALE]:
                # 平移和缩放模式都使用浮动坐标系的轴检测
                return self.detect_floating_axis(mouse_pos)
            elif self.current_mode == OperationMode.MODE_ROTATE:
                # 旋转模式使用旋转轴检测
                return self._detect_rotation_axis(mouse_pos, self.selected_geo.position)
                
            return -1
        except Exception as e:
            print(f"轴检测出错: {str(e)}")
            return -1

    def _detect_scale_axis(self, mouse_pos, position):
        """检测鼠标是否在缩放控件上"""
        # 获取射线信息
        ray_origin, ray_direction = self._get_mouse_ray(mouse_pos)
        
        # 初始化结果
        active_axis = -1
        min_distance = float('inf')
        
        # 控件尺寸（应与_draw_scale_gizmo中一致）
        axis_length = 1.5
        axis_radius = 0.03
        box_size = 0.1
        central_box_size = 0.15
        
        # 检查三个轴向的圆柱体
        axis_directions = [
            np.array([1, 0, 0]),  # X轴
            np.array([0, 1, 0]),  # Y轴
            np.array([0, 0, 1])   # Z轴
        ]
        
        # 对每个轴进行检查
        for i, direction in enumerate(axis_directions):
            # 计算轴的起点和终点
            start_point = position
            end_point = position + direction * axis_length
            
            # 检测射线与圆柱体相交
            result = self._ray_cylinder_intersection(
                ray_origin, ray_direction, 
                start_point, end_point, 
                axis_radius
            )
            
            # 如果相交，检查距离
            if result is not None:
                # 确保我们接收到的是数字距离而不是字典
                t = result
                if isinstance(result, dict) and 'distance' in result:
                    t = result['distance']
                elif isinstance(result, (list, tuple, np.ndarray)) and len(result) > 3:
                    t = result[3]  # 假设第四个元素是距离
                    
                # 检查这个距离是否是最近的
                if t is not None and isinstance(t, (int, float)) and t > 0 and t < min_distance:
                    min_distance = t
                    active_axis = i
        
        # 检查中心的统一缩放控件
        box_center = position
        box_half_size = np.array([central_box_size/2, central_box_size/2, central_box_size/2])
        
        result = self._ray_box_intersection(ray_origin, ray_direction, box_center, box_half_size)
        
        if result is not None and result > 0 and result < min_distance:
            min_distance = result
            active_axis = 3  # 统一缩放的特殊索引
        
        return active_axis

    def _ray_box_intersection(self, ray_origin, ray_direction, box_center, half_size):
        """计算射线与盒子的相交距离"""
        # 计算射线与盒子的相对位置
        min_point = box_center - half_size
        max_point = box_center + half_size
        
        # 计算与各个面的相交时间
        t_min = float('-inf')
        t_max = float('inf')
        
        for i in range(3):
            if abs(ray_direction[i]) < 1e-6:
                # 射线平行于这个轴的面
                if ray_origin[i] < min_point[i] or ray_origin[i] > max_point[i]:
                    return -1  # 没有相交
            else:
                t1 = (min_point[i] - ray_origin[i]) / ray_direction[i]
                t2 = (max_point[i] - ray_origin[i]) / ray_direction[i]
                
                if t1 > t2:
                    t1, t2 = t2, t1
                    
                t_min = max(t_min, t1)
                t_max = min(t_max, t2)
                
                if t_min > t_max:
                    return -1  # 没有相交
        
        # 返回相交距离
        return t_min if t_min > 0 else t_max

    def _handle_floating_scale_drag(self, dx, dy):
        """处理浮动坐标轴的缩放拖拽"""
        if not self.selected_geo or not hasattr(self, 'active_axis'):
            return
            
        try:
            # 获取当前选中的轴
            if not hasattr(self, 'gizmo_geometries'):
                return
                
            # 将轴名称转换为索引
            axis_name = None
            if isinstance(self.active_axis, str):
                axis_name = self.active_axis
            else:
                # 如果是数字索引，确保在有效范围内
                if self.active_axis >= 0 and self.active_axis < len(self.gizmo_geometries):
                    axis_name = self.gizmo_geometries[self.active_axis][0]
            
            if not axis_name:
                return
                
            # 计算缩放因子
            scale_speed = 0.01
            
            # 从相机属性获取信息
            camera_pos = np.array(self.camera_config['position'])
            camera_target = np.array(self._camera_target)  # 使用_camera_target属性
            
            # 获取视图方向
            view_dir = camera_target - camera_pos
            view_dir = view_dir / np.linalg.norm(view_dir)
            
            # 获取轴方向
            axis_dir = None
            if axis_name == 'x':
                axis_dir = np.array([1, 0, 0])
            elif axis_name == 'y':
                axis_dir = np.array([0, 1, 0])
            elif axis_name == 'z':
                axis_dir = np.array([0, 0, 1])
                
            # 计算视图与轴的点积，决定拖动方向
            view_dot = np.dot(view_dir, axis_dir)
            
            # 根据视图和轴的关系决定使用哪个方向的拖动值
            if abs(view_dot) < 0.5:  # 视图方向与轴近乎垂直
                drag_amount = -dy * scale_speed
            else:
                # 根据视图方向决定水平拖动的正负号
                sign = -1 if view_dot < 0 else 1
                drag_amount = dx * scale_speed * sign
            
            # 获取当前尺寸
            current_size = list(self.selected_geo.size)
            
            # 根据轴更新相应维度的尺寸
            axis_index = {'x': 0, 'y': 1, 'z': 2}[axis_name]
            current_size[axis_index] += drag_amount
            
            # 确保尺寸不会太小
            current_size[axis_index] = max(0.1, current_size[axis_index])
            
            # 应用新的尺寸
            self.selected_geo.size = current_size
            
            # 如果是组，更新子对象的变换
            if self.selected_geo.type == "group":
                if hasattr(self.selected_geo, '_update_transform'):
                    self.selected_geo._update_transform()
                if hasattr(self.selected_geo, '_update_children_transforms'):
                    self.selected_geo._update_children_transforms()
                
        except Exception as e:
            print(f"缩放拖拽出错: {str(e)}")
            import traceback
            traceback.print_exc()

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
                    target_obj.children.append(new_obj)
                else:
                    self.gl_widget.geometries.append(new_obj)
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
                target_obj.children.append(new_obj)
            else:
                self.gl_widget.geometries.append(new_obj)
        
        # 刷新视图
        self.refresh()
        self.gl_widget.geometriesChanged.emit()

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
                    target_obj.children.append(new_obj)
                else:
                    self.gl_widget.geometries.append(new_obj)
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
                target_obj.children.append(new_obj)
            else:
                self.gl_widget.geometries.append(new_obj)
        
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

    def _handle_context_action(self, action_data):
        """处理右键菜单动作"""
        action, obj = action_data
        
        # 检查是否是多选状态
        has_multi_selection = len(self.gl_widget.selected_geos) > 1
        
        if action == "copy":
            if has_multi_selection:
                self._execute_multi_selection_action(self._copy_object)
            else:
                self._copy_object(obj)
                
        elif action == "paste":
            if has_multi_selection:
                self._execute_multi_selection_action(self._paste_object, obj)
            else:
                self._paste_object(obj)
                
        elif action == "delete":
            if has_multi_selection:
                self._execute_multi_selection_action(self._delete_object)
            else:
                self._delete_object(obj)
                
        elif action == "rename":
            if has_multi_selection:
                self._execute_multi_selection_action(self._rename_object)
            else:
                self._rename_object(obj)
                
        elif action == "add_geometry":
            geo_type = obj  # 在这种情况下，obj是几何体类型
            if has_multi_selection:
                self._execute_multi_selection_action(self._add_geometry_to_group, geo_type)
            else:
                self._add_geometry_to_group(self.gl_widget.selected_geo, geo_type)
                
        elif action == "add_group":
            if has_multi_selection:
                self._execute_multi_selection_action(self._add_group_to_group)
            else:
                self._add_group_to_group(obj)

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
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        # 添加导出到Mujoco XML选项
        export_mujoco_action = file_menu.addAction("导出为Mujoco XML...")
        export_mujoco_action.triggered.connect(self.export_to_mujoco)

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
                elem = ET.SubElement(parent_elem, "Group")
                elem.set("name", obj.name)
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
                # 几何体对象
                elem = ET.SubElement(parent_elem, "Geometry")
                elem.set("name", obj.name)
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