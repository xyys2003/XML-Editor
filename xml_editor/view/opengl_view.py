"""
OpenGL视图

负责场景的3D渲染和用户交互。
"""

from PyQt5.QtWidgets import QOpenGLWidget, QSizePolicy
from PyQt5.QtCore import Qt, QSize, QPoint, pyqtSignal
from PyQt5.QtGui import QMouseEvent, QWheelEvent, QKeyEvent

import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *  # 添加GLUT库导入

from ..model.geometry import GeometryType, OperationMode
from ..viewmodel.scene_viewmodel import SceneViewModel
from ..model.raycaster import GeometryRaycaster, RaycastResult
from ..model.geometry import Geometry

# 初始化GLUT
try:
    glutInit()
except Exception as e:
    print(f"警告: 无法初始化GLUT: {e}")
    raise e

class OpenGLView(QOpenGLWidget):
    """
    OpenGL视图类
    
    负责渲染3D场景并处理用户交互
    """
    # 信号
    mousePressed = pyqtSignal(QMouseEvent)
    mouseReleased = pyqtSignal(QMouseEvent)
    mouseMoved = pyqtSignal(QMouseEvent)
    mouseWheel = pyqtSignal(QWheelEvent)
    keyPressed = pyqtSignal(QKeyEvent)
    
    def __init__(self, scene_viewmodel: SceneViewModel, parent=None):
        """
        初始化OpenGL视图
        
        参数:
            scene_viewmodel: 场景视图模型的引用
            parent: 父窗口部件
        """
        super().__init__(parent)
        self._scene_viewmodel = scene_viewmodel
        
        # 设置尺寸策略
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(QSize(400, 300))
        
        # 鼠标交互相关
        self._last_mouse_pos = QPoint()
        self._is_mouse_pressed = False
        self._is_shift_pressed = False
        
        # 摄像机参数
        self._camera_distance = 10.0
        self._camera_rotation_x = 30.0  # 俯仰角
        self._camera_rotation_y = -45.0  # 偏航角
        self._camera_target = np.array([0.0, 0.0, 0.0])
        
        # 连接信号
        self._scene_viewmodel.geometriesChanged.connect(self.update)
        self._scene_viewmodel.selectionChanged.connect(self._on_selection_changed)
        self._scene_viewmodel.objectChanged.connect(self._on_object_changed)  # 监听对象变化信号
        self._scene_viewmodel.operationModeChanged.connect(self._on_operation_mode_changed)  # 监听操作模式变化信号

        # 捕获焦点
        self.setFocusPolicy(Qt.StrongFocus)
        
        # 变换控制器状态
        self._dragging_controller = False
        self._controller_axis = None  # 'x', 'y', 'z' 或 None
        self._drag_start_pos = None
        self._drag_start_value = None
        
        # 坐标系选择 (True: 局部坐标系, False: 全局坐标系)
        self._use_local_coords = False

        # 射线投射器
        self._controllor_raycaster = None
        self._controller_geometries = []
    
    def minimumSizeHint(self):
        """返回建议的最小尺寸"""
        return QSize(200, 150)
    
    def sizeHint(self):
        """返回建议的尺寸"""
        return QSize(640, 480)
    
    def initializeGL(self):
        """初始化OpenGL上下文"""
        glClearColor(0.2, 0.2, 0.2, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_NORMALIZE)
        glEnable(GL_COLOR_MATERIAL)
        
        # 设置光源
        glLightfv(GL_LIGHT0, GL_POSITION, [1.0, 1.0, 1.0, 0.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 1.0, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
        
        # 启用混合（用于半透明物体）
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    
    def resizeGL(self, width, height):
        """处理窗口大小变化事件"""
        glViewport(0, 0, width, height)
        self._update_projection(width, height)
    
    def paintGL(self):
        """渲染场景"""
        # 清除缓冲区
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        # 设置投影矩阵
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        self._update_projection(self.width(), self.height())
        
        # 设置模型视图矩阵
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        # 更新摄像机配置到场景视图模型
        self._update_camera_config()
        
        # 渲染顺序：先绘制网格和几何体
        
        # 绘制网格
        self._draw_grid()
        
        # 绘制场景中的几何体
        for geometry in self._scene_viewmodel.geometries:
            self._draw_geometry(geometry)
            
        # 渲染坐标系和控制器，确保它们始终可见
        
        # 绘制世界坐标轴（禁用深度测试，确保始终可见）
        glDisable(GL_DEPTH_TEST)
        self._draw_axes()
        glEnable(GL_DEPTH_TEST)
        
        # 如果有选中的对象且处于操作模式，直接绘制变换控制器
        selected_geo = self._scene_viewmodel.selected_geometry
        if selected_geo and self._scene_viewmodel.operation_mode != OperationMode.OBSERVE and selected_geo.visible:
            glDisable(GL_DEPTH_TEST)
            self._draw_transform_controller(selected_geo)
            glEnable(GL_DEPTH_TEST)
    
    def _update_projection(self, width, height):
        """更新投影矩阵"""
        aspect = width / height if height > 0 else 1.0
        gluPerspective(45.0, aspect, 0.1, 100.0)
    
    def _update_camera_config(self):
        """更新摄像机配置到场景视图模型"""
        # 计算摄像机位置
        camera_x = self._camera_target[0] + self._camera_distance * np.cos(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x))
        camera_y = self._camera_target[1] + self._camera_distance * np.sin(np.radians(self._camera_rotation_x))
        camera_z = self._camera_target[2] + self._camera_distance * np.sin(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x))

        # 设置视图
        gluLookAt(
            camera_x, camera_y, camera_z,                   # 摄像机位置
            self._camera_target[0], self._camera_target[1], self._camera_target[2],  # 目标点
            0.0, 1.0, 0.0                                  # 上向量
        )

        camera_position = np.array([camera_x, camera_y, camera_z])
        
        # 获取当前的投影矩阵和模型视图矩阵
        projection_matrix = glGetDoublev(GL_PROJECTION_MATRIX).T
        modelview_matrix = glGetDoublev(GL_MODELVIEW_MATRIX).T
        
        # 更新场景视图模型的摄像机配置
        self._scene_viewmodel.set_camera_config({
            'position': camera_position,
            'target': self._camera_target,
            'up': np.array([0.0, 1.0, 0.0]),
            'projection_matrix': projection_matrix,
            'view_matrix': modelview_matrix
        })
    
    def _draw_grid(self):
        """绘制地面网格"""
        glDisable(GL_LIGHTING)
        
        # 将网格线设为更透明
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(0.5, 0.5, 0.5, 0.3)  # 灰色，更低的透明度
        
        glBegin(GL_LINES)
        
        # 绘制x轴线
        for i in range(-10, 11):
            glVertex3f(i, 0, -10)
            glVertex3f(i, 0, 10)
        
        # 绘制z轴线
        for i in range(-10, 11):
            glVertex3f(-10, 0, i)
            glVertex3f(10, 0, i)
            
        glEnd()
        
        glEnable(GL_LIGHTING)
    
    def _draw_axes(self):
        """绘制坐标轴"""
        glDisable(GL_LIGHTING)

        glLineWidth(1.0)
        
        glBegin(GL_LINES)
        
        # X轴（红色）
        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(0, 0, 0)
        glVertex3f(1., 0, 0)
        
        # Y轴（绿色）
        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 1., 0)
        
        # Z轴（蓝色）
        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 0, 1.)
        
        glEnd()
        
        # 绘制轴端小锥体增强可视性
        
        # X轴锥体（红色）
        glColor3f(1.0, 0.0, 0.0)
        glPushMatrix()
        glTranslatef(1., 0, 0)
        glRotatef(90, 0, 1, 0)
        try:
            glutSolidCone(0.08, 0.2, 8, 8)
        except Exception:
            pass
        glPopMatrix()
        
        # Y轴锥体（绿色）
        glColor3f(0.0, 1.0, 0.0)
        glPushMatrix()
        glTranslatef(0, 1., 0)
        glRotatef(-90, 1, 0, 0)
        try:
            glutSolidCone(0.08, 0.2, 8, 8)
        except Exception:
            pass
        glPopMatrix()
        
        # Z轴锥体（蓝色）
        glColor3f(0.0, 0.0, 1.0)
        glPushMatrix()
        glTranslatef(0, 0, 1.)
        try:
            glutSolidCone(0.08, 0.2, 8, 8)
        except Exception:
            pass
        glPopMatrix()
        
        glEnable(GL_LIGHTING)
    
    def _draw_geometry(self, geometry):
        """
        递归绘制几何体和其子对象
        
        参数:
            geometry: 要绘制的几何体
        """
        # 保存当前矩阵
        glPushMatrix()
        
        # 应用几何体的变换
        if hasattr(geometry, 'transform_matrix'):
            # 将NumPy矩阵转换为OpenGL兼容的格式
            geom_transform = geometry.transform_matrix.T.flatten().tolist()
            glMultMatrixf(geom_transform)
        
        # 绘制几何体
        if hasattr(geometry, 'type'):
            if geometry.type == 'group':
                # 绘制组的包围盒（半透明）
                self._draw_wireframe_cube(geometry.size[0], geometry.size[1], geometry.size[2], highlight=geometry == self._scene_viewmodel.selected_geometry)
            else:
                # 根据几何体类型和选中状态绘制
                self._draw_geometry_by_type(geometry, geometry == self._scene_viewmodel.selected_geometry)
        
        # 递归绘制子对象
        if hasattr(geometry, 'children'):
            for child in geometry.children:
                self._draw_geometry(child)
        
        # 恢复矩阵
        glPopMatrix()
    
    def _draw_geometry_by_type(self, geometry, selected):
        """
        根据几何体类型绘制
        
        参数:
            geometry: 要绘制的几何体
            selected: 是否被选中
        """
        # 检查可见性，如果不可见则直接返回
        if hasattr(geometry, 'visible') and not geometry.visible:
            return
            
        # 设置材质
        color = geometry.material.color
        
        # 如果被选中，增加亮度
        if selected:
            # 根据操作模式调整透明度
            if self._scene_viewmodel.operation_mode != OperationMode.OBSERVE:
                # 操作模式下使对象半透明
                glColor4f(min(color[0] + 0.2, 1.0), min(color[1] + 0.2, 1.0), min(color[2] + 0.2, 1.0), 0.5)
            else:
                glColor4f(min(color[0] + 0.2, 1.0), min(color[1] + 0.2, 1.0), min(color[2] + 0.2, 1.0), color[3])
        else:
            glColor4f(color[0], color[1], color[2], color[3])
        
        # 根据几何体类型绘制
        if geometry.type == GeometryType.BOX.value:
            self._draw_box(geometry.size[0], geometry.size[1], geometry.size[2])
        elif geometry.type == GeometryType.SPHERE.value:
            self._draw_sphere(geometry.size[0])
        elif geometry.type == GeometryType.CYLINDER.value:
            self._draw_cylinder(geometry.size[0], geometry.size[2])
        elif geometry.type == GeometryType.CAPSULE.value:
            self._draw_capsule(geometry.size[0], geometry.size[2])
        elif geometry.type == GeometryType.PLANE.value:
            self._draw_plane()
        else:
            # 默认使用立方体
            self._draw_box(geometry.size[0], geometry.size[1], geometry.size[2])
        
        # 如果被选中，绘制包围盒
        if selected:
            if geometry.type == GeometryType.CAPSULE.value:
                self._draw_wireframe_cube(geometry.size[0], geometry.size[1], geometry.size[2]+geometry.size[0], highlight=True)
            else:
                self._draw_wireframe_cube(geometry.size[0], geometry.size[1], geometry.size[2], highlight=True)
        
    def _draw_translation_gizmo(self):
        """绘制平移控制器"""
        glDisable(GL_LIGHTING)
        
        # 绘制X轴（红色）
        glColor3f(1.0, 0.0, 0.0)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(2, 0, 0)
        glEnd()
        
        # X轴箭头
        glPushMatrix()
        glTranslatef(2, 0, 0)
        glRotatef(90, 0, 1, 0)
        glutSolidCone(0.1, 0.3, 10, 10)
        glPopMatrix()
        
        # 绘制Y轴（绿色）
        glColor3f(0.0, 1.0, 0.0)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 2, 0)
        glEnd()
        
        # Y轴箭头
        glPushMatrix()
        glTranslatef(0, 2, 0)
        glRotatef(-90, 1, 0, 0)
        glutSolidCone(0.1, 0.3, 10, 10)
        glPopMatrix()
        
        # 绘制Z轴（蓝色）
        glColor3f(0.0, 0.0, 1.0)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 0, 2)
        glEnd()
        
        # Z轴箭头
        glPushMatrix()
        glTranslatef(0, 0, 2)
        glutSolidCone(0.1, 0.3, 10, 10)
        glPopMatrix()
        
        glEnable(GL_LIGHTING)
        
    def _draw_rotation_gizmo(self):
        """绘制旋转控制器"""
        glDisable(GL_LIGHTING)
        
        # X轴旋转环（红色）
        glColor3f(1.0, 0.0, 0.0)
        self._draw_rotation_ring(1.5, 0, 0, 1, 0, 0)
        
        # Y轴旋转环（绿色）
        glColor3f(0.0, 1.0, 0.0)
        self._draw_rotation_ring(1.5, 1, 0, 0, 0, 1, 0)
        
        # Z轴旋转环（蓝色）
        glColor3f(0.0, 0.0, 1.0)
        self._draw_rotation_ring(1.5, 0, 1, 0, 0, 0, 1)
        
        glEnable(GL_LIGHTING)
        
    def _draw_rotation_ring(self, radius, axis_x, axis_y, axis_z, up_x=0, up_y=1, up_z=0):
        """绘制旋转环"""
        segments = 32
        angle_step = 270.0 / segments
        
        glPushMatrix()
        
        # 对准轴方向
        if axis_x == 1:
            glRotatef(90, 0, 1, 0)
        elif axis_y == 1:
            glRotatef(90, 1, 0, 0)
        
        # 绘制半圆弧
        glBegin(GL_LINE_STRIP)
        for i in range(segments + 1):
            angle = i * angle_step
            x = radius * np.cos(np.radians(angle))
            y = radius * np.sin(np.radians(angle))
            glVertex3f(x, y, 0)
        glEnd()
        
        # 绘制箭头
        glPushMatrix()
        glTranslatef(radius, 0, 0)
        glRotatef(90, 1, 0, 0)
        glutSolidCone(0.1, 0.3, 10, 10)
        glPopMatrix()
        
        glPopMatrix()
        
    def _draw_scale_gizmo(self):
        """绘制缩放控制器"""
        glDisable(GL_LIGHTING)
        
        # X轴缩放控制（红色）
        glColor3f(1.0, 0.0, 0.0)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(1.5, 0, 0)
        glEnd()
        
        # X轴立方体手柄
        glPushMatrix()
        glTranslatef(1.5, 0, 0)
        glScalef(0.2, 0.2, 0.2)
        glutSolidCube(2.0)
        glPopMatrix()
        
        # Y轴缩放控制（绿色）
        glColor3f(0.0, 1.0, 0.0)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 1.5, 0)
        glEnd()
        
        # Y轴立方体手柄
        glPushMatrix()
        glTranslatef(0, 1.5, 0)
        glScalef(0.2, 0.2, 0.2)
        glutSolidCube(2.0)
        glPopMatrix()
        
        # Z轴缩放控制（蓝色）
        glColor3f(0.0, 0.0, 1.0)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 0, 1.5)
        glEnd()
        
        # Z轴立方体手柄
        glPushMatrix()
        glTranslatef(0, 0, 1.5)
        glScalef(0.2, 0.2, 0.2)
        glutSolidCube(2.0)
        glPopMatrix()
        
        glEnable(GL_LIGHTING)
    
    def _draw_box(self, x, y, z):
        """绘制立方体"""
        glPushMatrix()
        glScalef(x, y, z)
        glutSolidCube(2.0)

        glPopMatrix()
    
    def _draw_sphere(self, radius):
        """绘制球体"""
        glPushMatrix()
        sphere_radius = radius
        sphere_slices = 20
        sphere_stacks = 20
        glutSolidSphere(sphere_radius, sphere_slices, sphere_stacks)
        glPopMatrix()
    
    def _draw_cylinder(self, radius, height):
        """绘制圆柱体"""
        cylinder_radius = radius
        cylinder_height = height * 2.0
        cylinder_slices = 20
        cylinder_stacks = 1

        glPushMatrix()
        glTranslatef(0.0, 0.0, -cylinder_height/2.0)

        gluCylinder(
            gluNewQuadric(),      # 二次曲面对象
            cylinder_radius,      # 底部半径
            cylinder_radius,      # 顶部半径
            cylinder_height,      # 高度
            cylinder_slices,      # 径向细分
            cylinder_stacks       # 高度细分
        )
        
        # 绘制底部和顶部圆盖
        gluDisk(gluNewQuadric(), 0.0, cylinder_radius, cylinder_slices, 1)
        
        glTranslatef(0.0, 0.0, cylinder_height)
        gluDisk(gluNewQuadric(), 0.0, cylinder_radius, cylinder_slices, 1)
        
        glPopMatrix()
    
    def _draw_capsule(self, radius, height):
        """绘制胶囊体（简化为圆柱和两个半球）"""
        glPushMatrix()
        capsule_radius = radius
        capsule_height = height * 2.0
        capsule_slices = 20
        capsule_stacks = 1

        glTranslatef(0.0, 0.0, -capsule_height/2.0)

        if capsule_height > 0:
            # 绘制中间圆柱部分
            gluCylinder(
                gluNewQuadric(),      # 二次曲面对象
                capsule_radius,       # 底部半径
                capsule_radius,       # 顶部半径
                capsule_height,       # 高度
                capsule_slices,       # 径向细分
                capsule_stacks        # 高度细分
            )
        
        # 绘制底部半球
        sphere_stacks = 10
        gluSphere(gluNewQuadric(), capsule_radius, capsule_slices, sphere_stacks)
        
        # 绘制顶部半球
        glTranslatef(0.0, 0.0, capsule_height)
        gluSphere(gluNewQuadric(), capsule_radius, capsule_slices, sphere_stacks)
        
        glPopMatrix()
    
    def _draw_plane(self):
        """绘制平面"""
        glPushMatrix()
        glScalef(1.0, 1.0, 0.01)  # 使平面非常薄
        glutSolidCube(2.0)
        glPopMatrix()
    
    def _draw_wireframe_cube(self, x, y, z, highlight=False):
        """
        绘制线框立方体
        
        参数:
            highlight: 是否高亮显示
        """
        glDisable(GL_LIGHTING)
        
        if highlight:
            glColor4f(1.0, 1.0, 0.0, 1.0)  # 黄色
            glLineWidth(2.0)
        else:
            glColor4f(0.5, 0.5, 0.5, 0.7)  # 灰色
            glLineWidth(1.0)
        
        glPushMatrix()
        glScalef(x, y, z)
        
        glBegin(GL_LINES)
        # 底面
        glVertex3f(-1, -1, -1)
        glVertex3f(1, -1, -1)
        glVertex3f(1, -1, -1)
        glVertex3f(1, -1, 1)
        glVertex3f(1, -1, 1)
        glVertex3f(-1, -1, 1)
        glVertex3f(-1, -1, 1)
        glVertex3f(-1, -1, -1)
        
        # 顶面
        glVertex3f(-1, 1, -1)
        glVertex3f(1, 1, -1)
        glVertex3f(1, 1, -1)
        glVertex3f(1, 1, 1)
        glVertex3f(1, 1, 1)
        glVertex3f(-1, 1, 1)
        glVertex3f(-1, 1, 1)
        glVertex3f(-1, 1, -1)
        
        # 连接底面和顶面
        glVertex3f(-1, -1, -1)
        glVertex3f(-1, 1, -1)
        glVertex3f(1, -1, -1)
        glVertex3f(1, 1, -1)
        glVertex3f(1, -1, 1)
        glVertex3f(1, 1, 1)
        glVertex3f(-1, -1, 1)
        glVertex3f(-1, 1, 1)
        glEnd()
        
        glPopMatrix()
        
        glLineWidth(1.0)
        glEnable(GL_LIGHTING)
    
    def mousePressEvent(self, event):
        """处理鼠标按下事件"""
        self._last_mouse_pos = event.pos()
        self._is_mouse_pressed = True
        
        # 如果有选中的对象且处于操作模式，尝试拾取变换控制器
        selected_geo = self._scene_viewmodel.selected_geometry
        operation_mode = self._scene_viewmodel.operation_mode
        
        if selected_geo and operation_mode != OperationMode.OBSERVE and selected_geo.visible:
            # 射线投射，检查是否点击到了控制器
            result = self._pick_controller(event.x(), event.y())
            if result:
                self._dragging_controller = True
                self._controller_axis = result
                self._drag_start_pos = event.pos()
                
                # 记录拖动开始时的初始值
                if operation_mode == OperationMode.TRANSLATE:
                    self._drag_start_value = selected_geo.position.copy()
                elif operation_mode == OperationMode.ROTATE:
                    self._drag_start_value = selected_geo.rotation.copy()
                elif operation_mode == OperationMode.SCALE:
                    self._drag_start_value = selected_geo.size.copy()
                return
        
        # 选择对象
        if event.button() == Qt.LeftButton:
            self._scene_viewmodel.select_at(event.x(), event.y(), self.width(), self.height())
        
        # 发出信号
        self.mousePressed.emit(event)
        
        # 接收后续的鼠标移动事件
        self.setMouseTracking(True)
    
    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件"""
        self._is_mouse_pressed = False
        
        # 重置变换控制器状态
        if self._dragging_controller:
            self._dragging_controller = False
            self._controller_axis = None
            self._drag_start_pos = None
            self._drag_start_value = None
        
        # 发出信号
        self.mouseReleased.emit(event)
        
        # 不再跟踪鼠标移动
        self.setMouseTracking(False)
    
    def mouseMoveEvent(self, event):
        """处理鼠标移动事件"""
        dx = event.x() - self._last_mouse_pos.x()
        dy = event.y() - self._last_mouse_pos.y()
        
        # 如果正在拖动变换控制器
        if self._dragging_controller and self._controller_axis:
            selected_geo = self._scene_viewmodel.selected_geometry
            operation_mode = self._scene_viewmodel.operation_mode
            
            if selected_geo:
                # 处理不同的操作模式
                if operation_mode == OperationMode.TRANSLATE:
                    self._handle_translation_drag(selected_geo, dx, dy)
                elif operation_mode == OperationMode.ROTATE:
                    self._handle_rotation_drag(selected_geo, dx, dy)
                elif operation_mode == OperationMode.SCALE:
                    self._handle_scale_drag(selected_geo, dx, dy)
                
                # 强制更新界面
                self.update()
        # 如果鼠标按下，根据当前模式执行不同操作
        elif self._is_mouse_pressed:
            # 处理摄像机旋转（左键拖动）
            if event.buttons() & Qt.LeftButton:
                self._camera_rotation_y += dx * 0.5
                self._camera_rotation_x = max(-90, min(90, self._camera_rotation_x + dy * 0.5))
                self.update()
            
            # 处理摄像机平移（右键拖动）
            elif event.buttons() & Qt.RightButton:
                # 计算平移向量
                right_vector = np.array([
                    np.cos(np.radians(self._camera_rotation_y - 90)),
                    0,
                    np.sin(np.radians(self._camera_rotation_y - 90))
                ])
                
                up_vector = np.array([0, 1, 0])
                
                # 应用平移
                self._camera_target -= right_vector * dx * 0.001 * self._camera_distance
                self._camera_target += up_vector * dy * 0.001 * self._camera_distance
                
                self.update()
        
        # 更新鼠标位置
        self._last_mouse_pos = event.pos()
        
        # 发出信号
        self.mouseMoved.emit(event)
    
    def wheelEvent(self, event):
        """处理鼠标滚轮事件"""
        # 更新摄像机距离
        delta = event.angleDelta().y() / 120  # 标准化滚轮步长
        self._camera_distance *= 0.9 ** delta  # 放大/缩小10%
        
        # 限制距离范围
        self._camera_distance = max(0.1, min(100.0, self._camera_distance))
        
        self.update()
        
        # 发出信号
        self.mouseWheel.emit(event)
    
    def keyPressEvent(self, event):
        """处理键盘按下事件"""
        # 处理Shift键
        if event.key() == Qt.Key_Shift:
            self._is_shift_pressed = True
            
        # 按下空格键切换坐标系
        elif event.key() == Qt.Key_Space:
            self._use_local_coords = not self._use_local_coords
            self.update()
            
        # 按下Escape键取消选择
        elif event.key() == Qt.Key_Escape:
            self._scene_viewmodel.clear_selection()
        
        # 发出信号
        self.keyPressed.emit(event)
    
    def keyReleaseEvent(self, event):
        """处理键盘释放事件"""
        # 处理Shift键
        if event.key() == Qt.Key_Shift:
            self._is_shift_pressed = False
    
    def reset_camera(self):
        """重置摄像机到默认位置"""
        self._camera_distance = 10.0
        self._camera_rotation_x = 30.0
        self._camera_rotation_y = -45.0
        self._camera_target = np.array([0.0, 0.0, 0.0])
        self.update()
    
    def _on_selection_changed(self, selected_object):
        """处理选中对象变化事件"""
        self._update_controllor_raycaster()
        self.update()

    def _on_object_changed(self, obj):
        """处理对象属性变化事件"""
        if obj == self._scene_viewmodel.selected_geometry:
            self._update_controllor_raycaster()
        self.update()

    def _on_operation_mode_changed(self, mode):
        """处理操作模式变化事件"""
        self._update_controllor_raycaster()
        self.update()

    def _update_controllor_raycaster(self):
        """更新控制器射线投射器"""
        operation_mode = self._scene_viewmodel.operation_mode
        selected_geo = self._scene_viewmodel.selected_geometry
        
        # 清空现有的控制器几何体
        self._controller_geometries = []
        
        # 如果没有选中对象或者处于观察模式，不需要创建控制器
        if not selected_geo or operation_mode == OperationMode.OBSERVE or not selected_geo.visible:
            self._controllor_raycaster = None
            return

        # 获取控制器在世界空间中的位置
        if self._use_local_coords:
            # 使用局部坐标系
            controller_origin = selected_geo.get_world_position()
            # 获取局部坐标轴方向和变换矩阵
            local_x = selected_geo.transform_matrix[:3, 0]
            local_y = selected_geo.transform_matrix[:3, 1]
            local_z = selected_geo.transform_matrix[:3, 2]
            transform_matrix = selected_geo.transform_matrix
        else:
            # 使用全局坐标系
            controller_origin = selected_geo.get_world_position()
            local_x = np.array([1, 0, 0])
            local_y = np.array([0, 1, 0])
            local_z = np.array([0, 0, 1])
            # 创建只包含平移的变换矩阵
            transform_matrix = np.eye(4)
            transform_matrix[:3, 3] = controller_origin
        
        # 根据操作模式创建不同的控制器几何体
        if operation_mode == OperationMode.TRANSLATE:
            # 为X、Y、Z轴创建平移控制器几何体（长条状）
            x_axis = Geometry(
                geo_type="box",
                name="x_axis_controller",
                position=(1.0, 0, 0),  # 轴中点位置
                size=(2.0, 0.1, 0.1),  # 细长盒子
                rotation=(0, 0, 0)
            )
            x_axis.transform_matrix = transform_matrix
            
            y_axis = Geometry(
                geo_type="box",
                name="y_axis_controller",
                position=(0, 1.0, 0),
                size=(0.1, 2.0, 0.1),
                rotation=(0, 0, 0)
            )
            y_axis.transform_matrix = transform_matrix
            
            z_axis = Geometry(
                geo_type="box",
                name="z_axis_controller",
                position=(0, 0, 1.0),
                size=(0.1, 0.1, 2.0),
                rotation=(0, 0, 0)
            )
            z_axis.transform_matrix = transform_matrix
            
            # 箭头
            x_arrow = Geometry(
                geo_type="cone",
                name="x_arrow_controller",
                position=(2.0, 0, 0),
                size=(0.2, 0.2, 0.3),
                rotation=(0, 0, -90)
            )
            x_arrow.transform_matrix = transform_matrix
            
            y_arrow = Geometry(
                geo_type="cone",
                name="y_arrow_controller",
                position=(0, 2.0, 0),
                size=(0.2, 0.2, 0.3),
                rotation=(90, 0, 0)
            )
            y_arrow.transform_matrix = transform_matrix
            
            z_arrow = Geometry(
                geo_type="cone",
                name="z_arrow_controller",
                position=(0, 0, 2.0),
                size=(0.2, 0.2, 0.3),
                rotation=(0, 0, 0)
            )
            z_arrow.transform_matrix = transform_matrix
            
            self._controller_geometries = [x_axis, y_axis, z_axis, x_arrow, y_arrow, z_arrow]
        
        elif operation_mode == OperationMode.ROTATE:
            # 为X、Y、Z轴创建旋转控制器几何体（环状）
            radius = 1.5
            thickness = 0.1
            
            # 创建X轴旋转环（在YZ平面上）
            x_ring = Geometry(
                geo_type="torus",
                name="x_ring_controller",
                position=(0, 0, 0),
                size=(radius, thickness, thickness),
                rotation=(0, 90, 0)  # 旋转使环处于YZ平面
            )
            x_ring.transform_matrix = transform_matrix
            
            # 创建Y轴旋转环（在XZ平面上）
            y_ring = Geometry(
                geo_type="torus",
                name="y_ring_controller",
                position=(0, 0, 0),
                size=(radius, thickness, thickness),
                rotation=(90, 0, 0)  # 旋转使环处于XZ平面
            )
            y_ring.transform_matrix = transform_matrix
            
            # 创建Z轴旋转环（在XY平面上）
            z_ring = Geometry(
                geo_type="torus",
                name="z_ring_controller",
                position=(0, 0, 0),
                size=(radius, thickness, thickness),
                rotation=(0, 0, 0)  # 环已经在XY平面上
            )
            z_ring.transform_matrix = transform_matrix
            
            self._controller_geometries = [x_ring, y_ring, z_ring]
        
        elif operation_mode == OperationMode.SCALE:
            # 为X、Y、Z轴创建缩放控制器几何体（轴+立方体手柄）
            # 轴
            x_axis = Geometry(
                geo_type="box",
                name="x_scale_axis",
                position=(0.75, 0, 0),
                size=(1.5, 0.05, 0.05),
                rotation=(0, 0, 0)
            )
            x_axis.transform_matrix = transform_matrix
            
            y_axis = Geometry(
                geo_type="box",
                name="y_scale_axis",
                position=(0, 0.75, 0),
                size=(0.05, 1.5, 0.05),
                rotation=(0, 0, 0)
            )
            y_axis.transform_matrix = transform_matrix
            
            z_axis = Geometry(
                geo_type="box",
                name="z_scale_axis",
                position=(0, 0, 0.75),
                size=(0.05, 0.05, 1.5),
                rotation=(0, 0, 0)
            )
            z_axis.transform_matrix = transform_matrix
            
            # 立方体手柄
            x_handle = Geometry(
                geo_type="box",
                name="x_scale_handle",
                position=(1.5, 0, 0),
                size=(0.2, 0.2, 0.2),
                rotation=(0, 0, 0)
            )
            x_handle.transform_matrix = transform_matrix
            
            y_handle = Geometry(
                geo_type="box",
                name="y_scale_handle",
                position=(0, 1.5, 0),
                size=(0.2, 0.2, 0.2),
                rotation=(0, 0, 0)
            )
            y_handle.transform_matrix = transform_matrix
            
            z_handle = Geometry(
                geo_type="box",
                name="z_scale_handle",
                position=(0, 0, 1.5),
                size=(0.2, 0.2, 0.2),
                rotation=(0, 0, 0)
            )
            z_handle.transform_matrix = transform_matrix
            
            self._controller_geometries = [x_axis, y_axis, z_axis, x_handle, y_handle, z_handle]
        
        # 创建控制器射线投射器
        self._controllor_raycaster = GeometryRaycaster(self._scene_viewmodel._camera_config, self._controller_geometries)

    def _pick_controller(self, screen_x, screen_y):
        """
        检测是否点击到变换控制器
        
        参数:
            screen_x: 屏幕X坐标
            screen_y: 屏幕Y坐标
            
        返回:
            轴标识('x', 'y', 'z')或None
        """
        if self._controllor_raycaster is None:
            self._update_controllor_raycaster()
            self.update()

        # 使用控制器射线投射器进行检测
        result = self._controllor_raycaster.raycast(screen_x, screen_y, self.width(), self.height())
        
        if result.is_hit():
            # 根据命中的几何体名称确定轴
            geo_name = result.geometry.name
            if 'x_' in geo_name:
                return 'x'
            elif 'y_' in geo_name:
                return 'y'
            elif 'z_' in geo_name:
                return 'z'
        
        return None
        
    def _handle_translation_drag(self, geometry, dx, dy):
        """处理平移拖动"""
        # 根据拖动轴和摄像机方向计算拖动量
        drag_amount = self._calculate_drag_amount(dx, dy, 0.01)
        
        # 获取当前位置
        current_pos = geometry.position.copy()
        
        # 根据控制器轴应用拖动
        if self._controller_axis == 'x':
            if self._use_local_coords:
                # 局部坐标系
                local_x = geometry.transform_matrix[:3, 0]
                current_pos += local_x * drag_amount
            else:
                # 全局坐标系
                current_pos[0] += drag_amount
        elif self._controller_axis == 'y':
            if self._use_local_coords:
                # 局部坐标系
                local_y = geometry.transform_matrix[:3, 1]
                current_pos += local_y * drag_amount
            else:
                # 全局坐标系
                current_pos[1] += drag_amount
        elif self._controller_axis == 'z':
            if self._use_local_coords:
                # 局部坐标系
                local_z = geometry.transform_matrix[:3, 2]
                current_pos += local_z * drag_amount
            else:
                # 全局坐标系
                current_pos[2] += drag_amount
                
        # 更新几何体位置
        geometry.position = current_pos
        
    def _handle_rotation_drag(self, geometry, dx, dy):
        """处理旋转拖动"""
        # 根据拖动轴和摄像机方向计算旋转量（角度）
        rotation_amount = self._calculate_drag_amount(dx, dy, 0.5)
        
        # 获取当前旋转
        current_rotation = geometry.rotation.copy()
        
        # 根据控制器轴应用旋转
        if self._controller_axis == 'x':
            current_rotation[0] += rotation_amount
        elif self._controller_axis == 'y':
            current_rotation[1] += rotation_amount
        elif self._controller_axis == 'z':
            current_rotation[2] += rotation_amount
            
        # 更新几何体旋转
        geometry.rotation = current_rotation
        
    def _handle_scale_drag(self, geometry, dx, dy):
        """处理缩放拖动"""
        # 根据拖动轴和摄像机方向计算缩放量
        scale_amount = 1.0 + self._calculate_drag_amount(dx, dy, 0.01)
        
        # 获取当前缩放
        current_scale = geometry.size.copy()
        
        # 根据控制器轴应用缩放
        if self._controller_axis == 'x':
            current_scale[0] *= scale_amount
        elif self._controller_axis == 'y':
            current_scale[1] *= scale_amount
        elif self._controller_axis == 'z':
            current_scale[2] *= scale_amount
            
        # 更新几何体缩放
        geometry.size = current_scale
        
    def _calculate_drag_amount(self, dx, dy, sensitivity):
        """
        根据屏幕拖动量计算实际的拖动量
        
        参数:
            dx: 屏幕X方向拖动量
            dy: 屏幕Y方向拖动量
            sensitivity: 灵敏度系数
            
        返回:
            实际的拖动量
        """
        # 获取摄像机前向方向
        camera_forward = np.array([
            np.cos(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x)),
            np.sin(np.radians(self._camera_rotation_x)),
            np.sin(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x))
        ])
        
        # 获取摄像机右向方向
        camera_right = np.array([
            np.cos(np.radians(self._camera_rotation_y - 90)),
            0,
            np.sin(np.radians(self._camera_rotation_y - 90))
        ])
        
        # 获取摄像机上向方向
        camera_up = np.cross(camera_right, -camera_forward)
        camera_up = camera_up / np.linalg.norm(camera_up)
        
        # 控制器轴的方向（基于全局或局部坐标系）
        if self._controller_axis == 'x':
            if self._use_local_coords and self._scene_viewmodel.selected_geometry:
                axis_dir = self._scene_viewmodel.selected_geometry.transform_matrix[:3, 0]
            else:
                axis_dir = np.array([1, 0, 0])
        elif self._controller_axis == 'y':
            if self._use_local_coords and self._scene_viewmodel.selected_geometry:
                axis_dir = self._scene_viewmodel.selected_geometry.transform_matrix[:3, 1]
            else:
                axis_dir = np.array([0, 1, 0])
        elif self._controller_axis == 'z':
            if self._use_local_coords and self._scene_viewmodel.selected_geometry:
                axis_dir = self._scene_viewmodel.selected_geometry.transform_matrix[:3, 2]
            else:
                axis_dir = np.array([0, 0, 1])
        else:
            return 0
            
        # 计算在摄像机坐标系中的拖动方向
        drag_dir = camera_right * dx + camera_up * -dy
        
        # 投影到轴方向
        drag_amount = np.dot(drag_dir, axis_dir) * sensitivity
        
        return drag_amount
    
    def _draw_transform_controller(self, geometry):
        """
        直接绘制变换控制器（不受深度测试影响）
        
        参数:
            geometry: 选中的几何体
        """
        operation_mode = self._scene_viewmodel.operation_mode
        
        # 保存当前矩阵
        glPushMatrix()
        
        # 根据坐标系选择决定变换控制器的位置和方向
        if hasattr(self, '_use_local_coords') and self._use_local_coords:
            # 使用局部坐标系 - 使用物体的完整变换矩阵
            matrix = geometry.transform_matrix.T.flatten().tolist()
            glMultMatrixf(matrix)
        else:
            # 使用全局坐标系 - 只移动到物体位置，不旋转
            glTranslatef(*geometry.get_world_position())
        
        # 设置混合模式，使控制器在几何体上方清晰可见
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        if operation_mode == OperationMode.TRANSLATE:
            # 绘制平移控制器（三个轴）
            self._draw_translation_gizmo()
        elif operation_mode == OperationMode.ROTATE:
            # 绘制旋转控制器（三个环）
            self._draw_rotation_gizmo()
        elif operation_mode == OperationMode.SCALE:
            # 绘制缩放控制器（三个轴）
            self._draw_scale_gizmo()
        
        # 恢复矩阵
        glPopMatrix() 