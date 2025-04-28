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

# 在文件顶部添加导入语句
from scipy.spatial.transform import Rotation as R

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
        
        # 连接坐标系变化信号
        if hasattr(self._scene_viewmodel, 'coordinateSystemChanged'):
            self._scene_viewmodel.coordinateSystemChanged.connect(self._on_coordinate_system_changed)

        # 捕获焦点
        self.setFocusPolicy(Qt.StrongFocus)
        
        # 变换控制器状态
        self._dragging_controller = False
        self._controller_axis = None  # 'x', 'y', 'z' 或 None
        self._drag_start_pos = None
        self._drag_start_value = None
        
        # 坐标系选择 (True: 局部坐标系, False: 全局坐标系)
        self._use_local_coords = True

        # 射线投射器
        self._controllor_raycaster = None
        self._controller_geometries = []
        
        # 启用拖拽功能
        self.setAcceptDrops(True)
        
        # 拖拽预览数据
        self.drag_preview = {'active': False, 'position': None, 'type': None}

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
        
        # 在最后绘制拖拽预览
        if self.drag_preview['active'] and self.drag_preview['position'] is not None:
            glDisable(GL_DEPTH_TEST)
            self._draw_drag_preview()
            glEnable(GL_DEPTH_TEST)
    
    def _update_projection(self, width, height):
        """更新投影矩阵"""
        aspect = width / height if height > 0 else 1.0
        gluPerspective(45.0, aspect, 0.1, 100.0)
    
    def _update_camera_config(self):
        """更新摄像机配置到场景视图模型（基于Z轴向上的坐标系）"""
        # 计算摄像机位置，考虑Z轴向上的坐标系
        camera_x = self._camera_target[0] + self._camera_distance * np.cos(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x))
        camera_y = self._camera_target[1] + self._camera_distance * np.sin(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x))
        camera_z = self._camera_target[2] + self._camera_distance * np.sin(np.radians(self._camera_rotation_x))

        # 设置视图
        gluLookAt(
            camera_x, camera_y, camera_z,                   # 摄像机位置
            self._camera_target[0], self._camera_target[1], self._camera_target[2],  # 目标点
            0.0, 0.0, 1.0                                  # 上向量设置为Z轴
        )

        camera_position = np.array([camera_x, camera_y, camera_z])
        
        # 获取当前的投影矩阵和模型视图矩阵
        projection_matrix = glGetDoublev(GL_PROJECTION_MATRIX).T
        modelview_matrix = glGetDoublev(GL_MODELVIEW_MATRIX).T
        
        # 更新场景视图模型的摄像机配置
        self._scene_viewmodel.set_camera_config({
            'position': camera_position,
            'target': self._camera_target,
            'up': np.array([0.0, 0.0, 1.0]),  # 上向量设置为Z轴
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
        
        # 在XY平面上绘制网格（对应Z轴向上的坐标系）
        # 绘制x轴线
        for i in range(-10, 11):
            glVertex3f(i, -10, 0)  # 更改为XY平面
            glVertex3f(i, 10, 0)
        
        # 绘制y轴线
        for i in range(-10, 11):
            glVertex3f(-10, i, 0)  # 更改为XY平面
            glVertex3f(10, i, 0)
            
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
            geometry.update_transform_matrix()
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

        
        # 恢复矩阵
        glPopMatrix()

        if hasattr(geometry, 'children'):
            for child in geometry.children:
                self._draw_geometry(child)
    
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
        elif geometry.type == GeometryType.ELLIPSOID.value:
            self._draw_ellipsoid(geometry.size[0], geometry.size[1], geometry.size[2])
        else:
            # 默认使用立方体
            self._draw_box(geometry.size[0], geometry.size[1], geometry.size[2])
        
        # 如果被选中，绘制包围盒
        if selected:
            if geometry.type == GeometryType.CAPSULE.value:
                # 胶囊体的包围盒需要考虑半球部分
                self._draw_wireframe_cube(geometry.size[0], geometry.size[0], geometry.size[2]+ geometry.size[0], highlight=True)
            else:
                self._draw_wireframe_cube(geometry.size[0], geometry.size[1], geometry.size[2], highlight=True)
        
    def _draw_translation_gizmo(self):
        """绘制平移控制器"""
        glDisable(GL_LIGHTING)
        
        # 保存当前的线宽
        previous_line_width = glGetFloatv(GL_LINE_WIDTH)
        
        # 设置线宽
        glLineWidth(2.0)
        
        # 绘制X轴（红色）
        if self._controller_axis == 'x':
            # 高亮显示
            glColor3f(1.0, 0.7, 0.7)  # 浅红色
        else:
            glColor3f(1.0, 0.0, 0.0)  # 红色
        
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
        if self._controller_axis == 'y':
            # 高亮显示
            glColor3f(0.7, 1.0, 0.7)  # 浅绿色
        else:
            glColor3f(0.0, 1.0, 0.0)  # 绿色
        
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
        if self._controller_axis == 'z':
            # 高亮显示
            glColor3f(0.7, 0.7, 1.0)  # 浅蓝色
        else:
            glColor3f(0.0, 0.0, 1.0)  # 蓝色
        
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 0, 2)
        glEnd()
        
        # Z轴箭头
        glPushMatrix()
        glTranslatef(0, 0, 2)
        glutSolidCone(0.1, 0.3, 10, 10)
        glPopMatrix()
        
        # 恢复线宽
        glLineWidth(previous_line_width)
        
        glEnable(GL_LIGHTING)

    def _draw_rotation_gizmo(self):
        """绘制旋转控制器 - 使用与平移控制器相同的样式"""
        glDisable(GL_LIGHTING)
        
        # 保存当前的线宽
        previous_line_width = glGetFloatv(GL_LINE_WIDTH)
        
        # 设置线宽
        glLineWidth(2.0)
        
        # 绘制X轴（红色）
        if self._controller_axis == 'x':
            # 高亮显示
            glColor3f(1.0, 0.7, 0.7)  # 浅红色
        else:
            glColor3f(1.0, 0.0, 0.0)  # 红色
        
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
        if self._controller_axis == 'y':
            # 高亮显示
            glColor3f(0.7, 1.0, 0.7)  # 浅绿色
        else:
            glColor3f(0.0, 1.0, 0.0)  # 绿色
        
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
        if self._controller_axis == 'z':
            # 高亮显示
            glColor3f(0.7, 0.7, 1.0)  # 浅蓝色
        else:
            glColor3f(0.0, 0.0, 1.0)  # 蓝色
        
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 0, 2)
        glEnd()
        
        # Z轴箭头
        glPushMatrix()
        glTranslatef(0, 0, 2)
        glutSolidCone(0.1, 0.3, 10, 10)
        glPopMatrix()
        
        # 恢复线宽
        glLineWidth(previous_line_width)
        
        glEnable(GL_LIGHTING)

    def _draw_scale_gizmo(self):
        """绘制缩放控制器"""
        glDisable(GL_LIGHTING)
        
        # 保存当前的线宽
        previous_line_width = glGetFloatv(GL_LINE_WIDTH)
        
        # 设置线宽
        glLineWidth(2.0)
        
        # X轴缩放控制（红色）
        if self._controller_axis == 'x':
            glColor3f(1.0, 0.7, 0.7)  # 高亮显示（浅红色）
        else:
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
        if self._controller_axis == 'y':
            glColor3f(0.7, 1.0, 0.7)  # 高亮显示（浅绿色）
        else:
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
        if self._controller_axis == 'z':
            glColor3f(0.7, 0.7, 1.0)  # 高亮显示（浅蓝色）
        else:
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
        
        # 恢复线宽
        glLineWidth(previous_line_width)
        
        glEnable(GL_LIGHTING)
    
    def _draw_box(self, x, y, z):
        """绘制立方体"""
        glPushMatrix()
        
        # Mujoco 风格调整，大小是半长半宽半高
        mujoco_size = (x*2, y*2, z*2)
        
        # 使用缩放将单位立方体调整为所需大小
        glScalef(x, y, z)
        glutSolidCube(2.0)  # 使用2.0单位立方体以匹配Mujoco尺寸规范
        
        glPopMatrix()
    
    def _draw_sphere(self, radius):
        """绘制球体"""
        glPushMatrix()
        
        # 直接使用半径
        glutSolidSphere(radius, 32, 32)
        
        glPopMatrix()
    
    def _draw_cylinder(self, radius, height):
        """绘制圆柱体，使中心线沿着Z轴"""
        glPushMatrix()
        
        # 创建二次曲面对象
        quad = gluNewQuadric()
        
        # 在Z轴向上的坐标系中，不需要旋转，直接沿Z轴绘制
        # 圆柱体从-height到+height，中心在原点
        
        # 向下平移半高，使圆柱体中心位于原点
        glTranslatef(0, 0, -height)
        
        # 绘制圆柱体
        cylinder_height = height * 2.0  # 全高
        gluCylinder(quad, radius, radius, cylinder_height, 32, 32)
        
        # 绘制底部和顶部圆盖
        gluDisk(quad, 0, radius, 32, 32)
        
        glTranslatef(0, 0, cylinder_height)
        gluDisk(quad, 0, radius, 32, 32)
        
        # 删除二次曲面对象
        gluDeleteQuadric(quad)
        
        glPopMatrix()
    
    def _draw_capsule(self, radius, height):
        """绘制胶囊体（圆柱+两个半球），使中心线沿着Z轴"""
        glPushMatrix()
        
        # 创建二次曲面对象
        quad = gluNewQuadric()
        
        # 半高
        half_height = height
        
        # 绘制圆柱体部分（沿Z轴，中心位于原点）
        glPushMatrix()
        glTranslatef(0, 0, -half_height)  # 移动到圆柱体底部
        gluCylinder(quad, radius, radius, 2 * half_height, 32, 32)
        glPopMatrix()
        
        # 绘制底部半球（位于圆柱体底部）
        glPushMatrix()
        glTranslatef(0, 0, -half_height)  # 移动到圆柱体底部
        glRotatef(180, 1, 0, 0)  # 旋转使半球朝向-Z方向
        gluSphere(quad, radius, 32, 32)
        glPopMatrix()
        
        # 绘制顶部半球（位于圆柱体顶部）
        glPushMatrix()
        glTranslatef(0, 0, half_height)  # 移动到圆柱体顶部
        gluSphere(quad, radius, 32, 32)
        glPopMatrix()
        
        # 删除二次曲面对象
        gluDeleteQuadric(quad)
        
        glPopMatrix()
    
    def _draw_plane(self):
        """绘制平面"""
        glPushMatrix()
        
        # 水平平面，非常薄的半透明立方体
        # 设置半透明
        glColor4f(glGetMaterialfv(GL_FRONT, GL_DIFFUSE)[0],
                  glGetMaterialfv(GL_FRONT, GL_DIFFUSE)[1],
                  glGetMaterialfv(GL_FRONT, GL_DIFFUSE)[2],
                  0.5)  # 半透明
        
        # 使用固定大小而不是基于尺寸参数
        glScalef(5.0, 0.01, 5.0)  # 极大且极薄的平面
        glutSolidCube(2.0)
        
        glPopMatrix()
    
    def _draw_ellipsoid(self, x_radius, y_radius, z_radius):
        """绘制椭球体"""
        glPushMatrix()
        
        # 使用缩放将球体变形为椭球体
        glScalef(x_radius, y_radius, z_radius)
        glutSolidSphere(1.0, 32, 32)
        
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
            axis = self._pick_controller(event.x(), event.y())
            if axis:
                self._dragging_controller = True
                self._controller_axis = axis
                self._drag_start_pos = event.pos()
                self._drag_start_value = None  # 将在首次拖动时设置
                
                # 强制重绘以显示高亮效果
                self.update()
                return
        
        # 选择或取消选择对象
        if event.button() == Qt.LeftButton:
            # 获取当前鼠标位置的几何体
            clicked_geo = self._scene_viewmodel.get_geometry_at(event.x(), event.y(), self.width(), self.height())
            
            # 如果点击的是当前已选中的几何体，则取消选择
            if clicked_geo == self._scene_viewmodel.selected_geometry:
                self._scene_viewmodel.clear_selection()
            # 否则，选择点击的几何体
            elif clicked_geo:
                self._scene_viewmodel.selected_geometry = clicked_geo
            # 如果没有点击到任何几何体，清除选择
            else:
                self._scene_viewmodel.clear_selection()
        
        # 发出信号
        self.mousePressed.emit(event)
        
        # 接收后续的鼠标移动事件
        self.setMouseTracking(True)
    
    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件"""
        # 如果是在拖动控制器，则保存状态
        if self._is_mouse_pressed and self._dragging_controller:
            # 检查是否有选中的几何体和拖动开始值
            selected_geo = self._scene_viewmodel.selected_geometry
            if selected_geo and self._drag_start_value is not None:
                # 如果位置、旋转或缩放发生了变化，通知场景视图模型
                if self._scene_viewmodel.operation_mode == OperationMode.TRANSLATE:
                    # 通知位置变化
                    if hasattr(self._scene_viewmodel, 'notifyPositionChanged'):
                        self._scene_viewmodel.notifyPositionChanged(selected_geo)
                elif self._scene_viewmodel.operation_mode == OperationMode.ROTATE:
                    # 通知旋转变化
                    if hasattr(self._scene_viewmodel, 'notifyRotationChanged'):
                        self._scene_viewmodel.notifyRotationChanged(selected_geo)
                elif self._scene_viewmodel.operation_mode == OperationMode.SCALE:
                    # 通知缩放变化
                    if hasattr(self._scene_viewmodel, 'notifyScaleChanged'):
                        self._scene_viewmodel.notifyScaleChanged(selected_geo)
                
                # 通知对象发生变化
                self._scene_viewmodel.notify_object_changed(selected_geo)
                
                # 在拖动完成后触发状态记录（仅当有实际变化时）
                if hasattr(self._scene_viewmodel, 'control_viewmodel'):
                    self._scene_viewmodel.control_viewmodel._on_geometry_modified()
        
        self._is_mouse_pressed = False
        
        # 重置变换控制器状态
        if self._dragging_controller:
            self._dragging_controller = False
            self._controller_axis = None
            self._drag_start_pos = None
            self._drag_start_value = None
            
            # 强制重绘以移除高亮效果
            self.update()
        
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
                # 在Z轴向上的坐标系中，偏航角旋转仍然是绕Z轴
                self._camera_rotation_y -= dx * 0.5
                
                # 在Z轴向上的坐标系中，俯仰角是绕水平轴旋转
                # 限制俯仰角范围，防止万向锁
                new_pitch = self._camera_rotation_x + dy * 0.5
                self._camera_rotation_x = max(-89, min(89, new_pitch))
                
                self.update()
            
            # 处理摄像机平移（右键拖动）
            elif event.buttons() & Qt.RightButton:
                # 通过当前视角计算水平平移向量（垂直于视线方向和上向量）
                right_vector = np.array([
                    np.cos(np.radians(self._camera_rotation_y - 90)),
                    np.sin(np.radians(self._camera_rotation_y - 90)),
                    0  # Z分量为0，因为右向量应该与世界上向量垂直
                ])
                
                # 根据当前视角计算前向量（垂直于右向量和上向量）
                world_up = np.array([0, 0, 1])  # Z轴向上
                camera_forward = np.array([
                    np.cos(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x)),
                    np.sin(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x)),
                    np.sin(np.radians(self._camera_rotation_x))
                ])
                
                # 在当前相机水平面内平移，垂直方向使用世界上向量
                self._camera_target -= right_vector * dx * 0.01 * self._camera_distance
                # 根据是否正在向上/向下看，调整垂直平移方向
                vertical_dir = world_up if self._camera_rotation_x > 0 else -world_up
                self._camera_target -= world_up * dy * 0.01 * self._camera_distance
                
                self.update()
        
        # 更新鼠标位置
        self._last_mouse_pos = event.pos()
        
        # 发出信号
        self.mouseMoved.emit(event)
    
    def wheelEvent(self, event):
        """处理鼠标滚轮事件"""
        # 更新摄像机距离
        delta = event.angleDelta().y() / 120  # 标准化滚轮步长
        
        # 计算新的距离（指数缩放）
        new_distance = self._camera_distance * (0.9 ** delta)  # 放大/缩小10%
        
        # 设置合理的最小和最大距离限制
        MIN_DISTANCE = 0.5  # 最小距离，避免穿过物体
        MAX_DISTANCE = 100.0  # 最大距离，避免视角太远
        
        # 应用限制
        self._camera_distance = max(MIN_DISTANCE, min(MAX_DISTANCE, new_distance))
        
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
            
            # 在状态栏显示当前坐标系模式
            parent_window = self.window()
            if hasattr(parent_window, 'statusBar'):
                coord_system = "局部坐标系" if self._use_local_coords else "全局坐标系"
                parent_window.statusBar().showMessage(f"当前模式: {coord_system}", 2000)
            
            # 更新控制器显示
            self._update_controllor_raycaster()
            self.update()
            
            print(f"坐标系已切换为: {'局部坐标系' if self._use_local_coords else '全局坐标系'}")
            
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
        controller_origin = selected_geo.get_world_position()
        
        # 根据坐标系模式选择使用的坐标轴
        if self._use_local_coords:
            # 使用局部坐标系
            transform_matrix = selected_geo.transform_matrix.copy()
        else:
            # 使用全局坐标系
            transform_matrix = np.eye(4)
            transform_matrix[:3, 3] = controller_origin
        
        # 根据操作模式创建不同的控制器几何体
        if operation_mode == OperationMode.TRANSLATE:
            # 平移控制器代码不变...
            scale_factor = 2.0
            axis_length = 2.0 * scale_factor
            arrow_size = 0.25 * scale_factor
            
            # X轴
            x_axis = Geometry(
                geo_type="box",
                name="x_axis_controller",
                position=(axis_length/2, 0, 0),
                size=(axis_length/2, 0.05, 0.05),
                rotation=(0, 0, 0)
            )
            x_axis.tag = "x_axis"
            x_axis.material.color = (1.0, 0.0, 0.0, 1.0)  # 红色
            x_axis.transform_matrix = transform_matrix.copy()
            
            # X轴箭头
            x_arrow = Geometry(
                geo_type="box",
                name="x_arrow_controller",
                position=(axis_length, 0, 0),
                size=(arrow_size, arrow_size, arrow_size),
                rotation=(0, 0, 45)
            )
            x_arrow.tag = "x_axis"
            x_arrow.material.color = (1.0, 0.0, 0.0, 1.0)  # 红色
            x_arrow.transform_matrix = transform_matrix.copy()
            
            # Y轴
            y_axis = Geometry(
                geo_type="box",
                name="y_axis_controller",
                position=(0, axis_length/2, 0),
                size=(0.05, axis_length/2, 0.05),
                rotation=(0, 0, 0)
            )
            y_axis.tag = "y_axis"
            y_axis.material.color = (0.0, 1.0, 0.0, 1.0)  # 绿色
            y_axis.transform_matrix = transform_matrix.copy()
            
            # Y轴箭头
            y_arrow = Geometry(
                geo_type="box",
                name="y_arrow_controller",
                position=(0, axis_length, 0),
                size=(arrow_size, arrow_size, arrow_size),
                rotation=(0, 0, 45)
            )
            y_arrow.tag = "y_axis"
            y_arrow.material.color = (0.0, 1.0, 0.0, 1.0)  # 绿色
            y_arrow.transform_matrix = transform_matrix.copy()
            
            # Z轴
            z_axis = Geometry(
                geo_type="box",
                name="z_axis_controller",
                position=(0, 0, axis_length/2),
                size=(0.05, 0.05, axis_length/2),
                rotation=(0, 0, 0)
            )
            z_axis.tag = "z_axis"
            z_axis.material.color = (0.0, 0.0, 1.0, 1.0)  # 蓝色
            z_axis.transform_matrix = transform_matrix.copy()
            
            # Z轴箭头
            z_arrow = Geometry(
                geo_type="box",
                name="z_arrow_controller",
                position=(0, 0, axis_length),
                size=(arrow_size, arrow_size, arrow_size),
                rotation=(45, 0, 0)
            )
            z_arrow.tag = "z_axis"
            z_arrow.material.color = (0.0, 0.0, 1.0, 1.0)  # 蓝色
            z_arrow.transform_matrix = transform_matrix.copy()
            
            self._controller_geometries = [x_axis, x_arrow, y_axis, y_arrow, z_axis, z_arrow]
        
        elif operation_mode == OperationMode.ROTATE:
            # 完全照搬平移控制器的逻辑
            scale_factor = 2.0
            axis_length = 2.0 * scale_factor
            arrow_size = 0.25 * scale_factor
            
            # X轴旋转控制器（红色）
            x_axis = Geometry(
                geo_type="box",
                name="x_rotation_controller",
                position=(axis_length/2, 0, 0),
                size=(axis_length/2, 0.05, 0.05),
                rotation=(0, 0, 0)
            )
            x_axis.tag = "x_rotation"  # 使用不同的tag以区分平移控制器
            x_axis.material.color = (1.0, 0.0, 0.0, 1.0)  # 红色
            x_axis.transform_matrix = transform_matrix.copy()
            
            # X轴箭头
            x_arrow = Geometry(
                geo_type="box",
                name="x_rotation_arrow",
                position=(axis_length, 0, 0),
                size=(arrow_size, arrow_size, arrow_size),
                rotation=(0, 0, 45)
            )
            x_arrow.tag = "x_rotation"
            x_arrow.material.color = (1.0, 0.0, 0.0, 1.0)  # 红色
            x_arrow.transform_matrix = transform_matrix.copy()
            
            # Y轴旋转控制器（绿色）
            y_axis = Geometry(
                geo_type="box",
                name="y_rotation_controller",
                position=(0, axis_length/2, 0),
                size=(0.05, axis_length/2, 0.05),
                rotation=(0, 0, 0)
            )
            y_axis.tag = "y_rotation"
            y_axis.material.color = (0.0, 1.0, 0.0, 1.0)  # 绿色
            y_axis.transform_matrix = transform_matrix.copy()
            
            # Y轴箭头
            y_arrow = Geometry(
                geo_type="box",
                name="y_rotation_arrow",
                position=(0, axis_length, 0),
                size=(arrow_size, arrow_size, arrow_size),
                rotation=(0, 0, 45)
            )
            y_arrow.tag = "y_rotation"
            y_arrow.material.color = (0.0, 1.0, 0.0, 1.0)  # 绿色
            y_arrow.transform_matrix = transform_matrix.copy()
            
            # Z轴旋转控制器（蓝色）
            z_axis = Geometry(
                geo_type="box",
                name="z_rotation_controller",
                position=(0, 0, axis_length/2),
                size=(0.05, 0.05, axis_length/2),
                rotation=(0, 0, 0)
            )
            z_axis.tag = "z_rotation"
            z_axis.material.color = (0.0, 0.0, 1.0, 1.0)  # 蓝色
            z_axis.transform_matrix = transform_matrix.copy()
            
            # Z轴箭头
            z_arrow = Geometry(
                geo_type="box",
                name="z_rotation_arrow",
                position=(0, 0, axis_length),
                size=(arrow_size, arrow_size, arrow_size),
                rotation=(45, 0, 0)
            )
            z_arrow.tag = "z_rotation"
            z_arrow.material.color = (0.0, 0.0, 1.0, 1.0)  # 蓝色
            z_arrow.transform_matrix = transform_matrix.copy()
            
            self._controller_geometries = [x_axis, x_arrow, y_axis, y_arrow, z_axis, z_arrow]
        
        elif operation_mode == OperationMode.SCALE:
            # 缩放控制器代码不变...
            scale_factor = 2.0
            box_size = 0.25 * scale_factor
            axis_length = 2.0 * scale_factor
            
            # X轴
            x_axis = Geometry(
                geo_type="box",
                name="x_axis_controller",
                position=(axis_length/2, 0, 0),
                size=(axis_length/2, 0.05, 0.05),
                rotation=(0, 0, 0)
            )
            x_axis.tag = "x_axis"
            x_axis.material.color = (1.0, 0.5, 0.5, 1.0)  # 浅红色
            x_axis.transform_matrix = transform_matrix.copy()
            
            # X轴缩放盒
            x_box = Geometry(
                geo_type="box",
                name="x_box_controller",
                position=(axis_length, 0, 0),
                size=(box_size, box_size, box_size),
                rotation=(0, 0, 0)
            )
            x_box.tag = "x_axis"
            x_box.material.color = (1.0, 0.0, 0.0, 1.0)  # 红色
            x_box.transform_matrix = transform_matrix.copy()
            
            # Y轴
            y_axis = Geometry(
                geo_type="box",
                name="y_axis_controller",
                position=(0, axis_length/2, 0),
                size=(0.05, axis_length/2, 0.05),
                rotation=(0, 0, 0)
            )
            y_axis.tag = "y_axis"
            y_axis.material.color = (0.5, 1.0, 0.5, 1.0)  # 浅绿色
            y_axis.transform_matrix = transform_matrix.copy()
            
            # Y轴缩放盒
            y_box = Geometry(
                geo_type="box",
                name="y_box_controller",
                position=(0, axis_length, 0),
                size=(box_size, box_size, box_size),
                rotation=(0, 0, 0)
            )
            y_box.tag = "y_axis"
            y_box.material.color = (0.0, 1.0, 0.0, 1.0)  # 绿色
            y_box.transform_matrix = transform_matrix.copy()
            
            # Z轴
            z_axis = Geometry(
                geo_type="box",
                name="z_axis_controller",
                position=(0, 0, axis_length/2),
                size=(0.05, 0.05, axis_length/2),
                rotation=(0, 0, 0)
            )
            z_axis.tag = "z_axis"
            z_axis.material.color = (0.5, 0.5, 1.0, 1.0)  # 浅蓝色
            z_axis.transform_matrix = transform_matrix.copy()
            
            # Z轴缩放盒
            z_box = Geometry(
                geo_type="box",
                name="z_box_controller",
                position=(0, 0, axis_length),
                size=(box_size, box_size, box_size),
                rotation=(0, 0, 0)
            )
            z_box.tag = "z_axis"
            z_box.material.color = (0.0, 0.0, 1.0, 1.0)  # 蓝色
            z_box.transform_matrix = transform_matrix.copy()
            
            self._controller_geometries = [x_axis, x_box, y_axis, y_box, z_axis, z_box]
        
        # 创建控制器射线投射器
        self._controllor_raycaster = GeometryRaycaster(
            self._scene_viewmodel._camera_config, 
            self._controller_geometries
        )

    def _pick_controller(self, screen_x, screen_y, just_hover=False):
        """检测是否点击到变换控制器"""
        if self._controllor_raycaster is None:
            self._update_controllor_raycaster()
        
        if self._controllor_raycaster is None:
            return None
        
        # 如果仅检测悬停，不重置控制器状态
        if not just_hover:
            # 重置控制器轴和拖动状态
            self._controller_axis = None
            self._drag_operation = None
            self._initial_value = None
        
        # 获取当前选中的对象
        selected_obj = self._scene_viewmodel.selected_geometry

       
        if not selected_obj:
            return None
        
        try:
            # 使用控制器射线投射器检测点击
            result = self._controllor_raycaster.raycast(screen_x, screen_y, self.width(), self.height())
            
            if result and result.is_hit():
                # 查找控制器类型
                geo = result.geometry
                
                # 记录初始值，用于撤销功能
                operation_mode = self._scene_viewmodel.operation_mode
                
                if operation_mode == OperationMode.TRANSLATE:
                    if not just_hover:
                        self._drag_operation = "translate"
                        self._initial_value = selected_obj.position.copy()
                
                elif operation_mode == OperationMode.ROTATE:
                    if not just_hover:
                        self._drag_operation = "rotate"
                        self._initial_value = selected_obj.rotation.copy()
                    
                    # 旋转控制器轴检测（基于tag）
                    if hasattr(geo, 'tag'):
                        tag = geo.tag
                        if 'x_rotation' in tag:
                            self._controller_axis = 'x'
                            return 'x'
                        elif 'y_rotation' in tag:
                            self._controller_axis = 'y'
                            return 'y'
                        elif 'z_rotation' in tag:
                            self._controller_axis = 'z'
                            return 'z'
                
                elif operation_mode == OperationMode.SCALE:
                    if not just_hover:
                        self._drag_operation = "scale"
                        self._initial_value = selected_obj.size.copy()
                
                # 标准轴检测
                if hasattr(geo, 'tag'):
                    tag = geo.tag
                    if 'x_axis' in tag:
                        self._controller_axis = 'x'
                        return 'x'
                    elif 'y_axis' in tag:
                        self._controller_axis = 'y'
                        return 'y'
                    elif 'z_axis' in tag:
                        self._controller_axis = 'z'
                        return 'z'
        except Exception as e:
            print(f"控制器拾取错误: {e}")
            import traceback
            traceback.print_exc()
        
        # 没有点击到控制器
        return None

    def _handle_translation_drag(self, geometry, dx, dy):
        """处理平移拖动"""
        # 根据拖动轴和摄像机方向计算拖动量
        drag_amount = self._calculate_drag_amount(dx, dy, 0.015)  # 灵敏度系数
        
        # 记录操作前的值（用于撤销功能）
        if self._drag_start_value is None:
            self._drag_start_value = geometry.position.copy()
        
        # 根据当前坐标系模式调用相应的处理函数
        if self._use_local_coords:
            self._handle_local_translation(geometry, drag_amount)
        else:
            self._handle_global_translation(geometry, drag_amount)
        
        # 通知视图模型对象已更改
        self._scene_viewmodel.notify_object_changed(geometry)
        
        # 在拖动完成后触发状态记录
        if hasattr(self._scene_viewmodel, 'control_viewmodel'):
            self._scene_viewmodel.control_viewmodel._on_geometry_modified()

    def _handle_local_translation(self, geometry, drag_amount):
        """
        处理局部坐标系中的平移 - 基于简化旋转逻辑
        
        关键思路：
        1. 基于对象自身的欧拉角创建局部旋转矩阵
        2. 从旋转矩阵中提取局部坐标轴
        3. 沿着局部坐标轴计算平移向量
        4. 直接更新物体位置属性
        """
        # 获取对象自身的欧拉角
        euler_angles = geometry.rotation
        
        # 创建对象自身的旋转矩阵
        rot_matrix = R.from_euler('XYZ', euler_angles, degrees=True).as_matrix()
        
        # 确定局部坐标系中的平移轴
        if self._controller_axis == 'x':
            local_axis = rot_matrix[:, 0]  # 局部X轴
        elif self._controller_axis == 'y':
            local_axis = rot_matrix[:, 1]  # 局部Y轴
        elif self._controller_axis == 'z':
            local_axis = rot_matrix[:, 2]  # 局部Z轴
        else:
            return
            
        # 计算平移向量（沿局部轴方向）
        translation_vector = local_axis * drag_amount
        
        # 直接将平移向量添加到当前位置
        new_position = [
            geometry.position[0] - translation_vector[0],
            geometry.position[1] - translation_vector[1],
            geometry.position[2] + translation_vector[2]
        ]
        
        # 更新几何体位置
        geometry.position = new_position

    def _handle_global_translation(self, geometry, drag_amount):
        """
        处理全局坐标系中的平移
        
        关键思路：
        1. 获取物体世界矩阵和父对象世界矩阵
        2. 确定全局坐标轴
        3. 将全局平移转换到局部坐标系
        4. 更新物体局部位置
        """
        
        # 确定全局坐标系中的平移轴
        if self._controller_axis == 'x':
            global_axis = np.array([1, 0, 0])  # 全局X轴
        elif self._controller_axis == 'y':
            global_axis = np.array([0, 1, 0])  # 全局Y轴
        elif self._controller_axis == 'z':
            global_axis = np.array([0, 0, 1])  # 全局Z轴
        else:
            return
            
        # 计算平移向量（沿全局轴方向）
        translation_vector = global_axis * drag_amount
        
        # 获取当前的世界矩阵
        world_matrix = self._get_world_matrix(geometry)
        
        # 从世界矩阵中提取当前世界位置
        current_geometry_pos= geometry.position



        # 计算局部坐标系下的新位置
        if geometry.parent is not None:
            # 获取父对象的世界矩阵
            parent_world_matrix = self._get_world_matrix(geometry.parent)
            
            # 获取父对象的旋转矩阵（3x3部分）
            parent_rotation = parent_world_matrix[:3, :3]
            
            # 将全局平移向量投影到父类旋转矩阵的三个轴上
            x_axis = parent_rotation[:, 0]  # 父类旋转后的X轴
            y_axis = parent_rotation[:, 1]  # 父类旋转后的Y轴
            z_axis = parent_rotation[:, 2]  # 父类旋转后的Z轴
            print(x_axis,y_axis,z_axis)
            # 计算投影分量（点积）
            x_component = np.dot(translation_vector, x_axis)
            y_component = np.dot(translation_vector, y_axis)
            z_component = np.dot(translation_vector, z_axis)
            
            # 使用投影分量作为新的局部平移向量
            local_translation = [x_component, y_component, z_component]
            print("local",x_component,y_component,z_component)
            print(translation_vector[0],translation_vector[1],translation_vector[2])
            # 计算新的局部位置
            new_position = [
                current_geometry_pos[0] - local_translation[0],
                current_geometry_pos[1] - local_translation[1],
                current_geometry_pos[2] + local_translation[2]
            ]
        else:
            # 如果没有父对象，直接使用全局平移向量
            new_position = [
                current_geometry_pos[0] - translation_vector[0],
                current_geometry_pos[1] - translation_vector[1],
                current_geometry_pos[2] + translation_vector[2]
            ]
        
        # 更新几何体位置 - 使用计算出的正确局部坐标位置
        geometry.position = new_position

    def _handle_rotation_drag(self, geometry, dx, dy):
        """处理旋转拖动"""
        # 计算拖动量
        drag_amount = self._calculate_drag_amount(dx, dy, 0.5)  # 旋转灵敏度
        
        # 记录操作前的值（用于撤销功能）
        if self._drag_start_value is None:
            self._drag_start_value = geometry.rotation.copy()
        
        # 根据当前坐标系模式调用相应的处理函数
        if self._use_local_coords:
            self._handle_local_rotation(geometry, drag_amount)
        else:
            self._handle_global_rotation(geometry, drag_amount)
        
        # 通知视图模型对象已更改
        self._scene_viewmodel.notify_object_changed(geometry)
        
        # 在拖动完成后触发状态记录
        if hasattr(self._scene_viewmodel, 'control_viewmodel'):
            self._scene_viewmodel.control_viewmodel._on_geometry_modified()

    def _handle_local_rotation(self, geometry, drag_amount):
        """
        处理局部坐标系中的旋转 - 正确处理存在父类的情况
        
        关键思路：
        1. 获取对象当前的全局位置作为旋转中心
        2. 基于对象自身的欧拉角创建局部旋转矩阵，不考虑父类旋转
        3. 确定在局部坐标系中的旋转轴
        4. 创建仅应用于对象自身的旋转增量矩阵
        5. 应用旋转并更新欧拉角
        """
        # 获取对象当前的全局位置作为旋转中心
        
        # 获取对象自身的欧拉角，不考虑父类旋转
        euler_angles = geometry.rotation
        
        # 创建对象自身的旋转矩阵
        rot_matrix = R.from_euler('XYZ', euler_angles, degrees=True).as_matrix()
        
        # 确定局部坐标系中的旋转轴
        if self._controller_axis == 'x':
            local_axis = rot_matrix[:, 0]  # 局部X轴
        elif self._controller_axis == 'y':
            local_axis = rot_matrix[:, 1]  # 局部Y轴
        elif self._controller_axis == 'z':
            local_axis = rot_matrix[:, 2]  # 局部Z轴
        else:
            return
            
        # 计算旋转变化（弧度）
        angle_rad = np.radians(drag_amount)
        
        # 创建增量旋转（基于局部坐标轴）
        delta_rotation = R.from_rotvec(local_axis * angle_rad)
        
        # 获取当前旋转
        current_rotation = R.from_euler('XYZ', euler_angles, degrees=True)
        
        # 将增量旋转应用到当前旋转 (delta_rotation * current_rotation)
        # 注意：先应用当前旋转，再应用增量旋转
        new_rotation = delta_rotation * current_rotation
        
        # 将新旋转转换为欧拉角（度数）
        new_euler_angles = new_rotation.as_euler('XYZ', degrees=True)
        
        # 更新几何体的旋转属性
        geometry.rotation = new_euler_angles.tolist()

    def _handle_global_rotation(self, geometry, drag_amount):
        """
        处理全局坐标系中的旋转
        
        关键思路：
        1. 在全局坐标系中计算旋转
        2. 计算旋转后的位置和方向
        3. 将结果转换回局部坐标系
        """
        # 计算旋转变化（弧度）
        angle_rad = np.radians(drag_amount)
        
        # 获取当前的世界矩阵和位置
        world_matrix = self._get_world_matrix(geometry)
        world_position = world_matrix[:3, 3]
        
        # 确定全局旋转轴和旋转中心
        if self._controller_axis == 'x':
            global_axis = np.array([1, 0, 0])
        elif self._controller_axis == 'y':
            global_axis = np.array([0, 1, 0])
        elif self._controller_axis == 'z':
            global_axis = np.array([0, 0, 1])
        else:
            return
        
        # 创建全局旋转矩阵
        global_rotation = R.from_rotvec(global_axis * angle_rad)
        
        # 获取当前的世界旋转
        current_world_rotation = R.from_matrix(world_matrix[:3, :3])
        
        # 计算新的世界旋转
        new_world_rotation = global_rotation * current_world_rotation
        
        # 计算新的世界位置（绕全局轴旋转）
        new_world_position = global_rotation.apply(world_position)
        
        if geometry.parent is not None:
            # 获取父对象的世界矩阵
            parent_world_matrix = self._get_world_matrix(geometry.parent)
            parent_inverse = np.linalg.inv(parent_world_matrix)
            
            # 将新的世界位置转换到局部坐标系
            temp_pos = np.append(new_world_position, 1.0)
            local_pos_homogeneous = np.dot(parent_inverse, temp_pos)
            new_local_position = local_pos_homogeneous[:3]
            
            # 计算局部旋转
            parent_rotation = R.from_matrix(parent_world_matrix[:3, :3])
            local_rotation = parent_rotation.inv() * new_world_rotation
            new_euler_angles = local_rotation.as_euler('XYZ', degrees=True)
            
            # 更新几何体的位置和旋转
            geometry.position = new_local_position.tolist()
            geometry.rotation = new_euler_angles.tolist()
        else:
            # 如果没有父节点，直接使用世界坐标
            geometry.position = new_world_position.tolist()
            geometry.rotation = new_world_rotation.as_euler('XYZ', degrees=True).tolist()

    def _handle_scale_drag(self, geometry, dx, dy):
        """处理缩放拖动"""
        # 计算缩放因子
        scale_factor = 1.0 + self._calculate_drag_amount(dx, dy, 0.015)
        
        # 记录操作前的值（用于撤销功能）
        if self._drag_start_value is None:
            self._drag_start_value = geometry.size.copy()
        
        # 根据当前坐标系模式调用相应的处理函数
        if self._use_local_coords:
            self._handle_local_scale(geometry, scale_factor)
        else:
            self._handle_global_scale(geometry, scale_factor)
        
        # 通知视图模型对象已更改
        self._scene_viewmodel.notify_object_changed(geometry)
        
        # 在拖动完成后触发状态记录
        if hasattr(self._scene_viewmodel, 'control_viewmodel'):
            self._scene_viewmodel.control_viewmodel._on_geometry_modified()

    def _handle_local_scale(self, geometry, scale_factor):
        """
        处理局部坐标系下的缩放
        
        Args:
            geometry: 几何体
            scale_factor: 缩放因子
        """
        # 直接修改几何体的大小，不涉及矩阵变换
        geometry.size = [
            geometry.size[0] * scale_factor,
            geometry.size[1] * scale_factor,
            geometry.size[2] * scale_factor
        ]
        # 修改此行：使用正确的方法名称
        self._scene_viewmodel.notify_object_changed(geometry)

    def _handle_global_scale(self, geometry, scale_factor):
        """
        处理全局坐标系下的缩放
        
        Args:
            geometry: 几何体
            scale_factor: 缩放因子
        """
        # 局部和全局缩放逻辑相同，直接调用局部缩放函数
        self._handle_local_scale(geometry, scale_factor)

    def _calculate_drag_amount(self, dx, dy, sensitivity):
        """
        根据屏幕拖动量计算实际的拖动量（基于Z轴向上的坐标系）
        
        参数:
            dx: 屏幕X方向拖动量
            dy: 屏幕Y方向拖动量
            sensitivity: 灵敏度系数
            
        返回:
            实际的拖动量
        """
        # 获取摄像机前向方向（Z轴向上坐标系）
        camera_forward = np.array([
            np.cos(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x)),
            np.sin(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x)),
            np.sin(np.radians(self._camera_rotation_x))
        ])
        
        # 获取摄像机右向量（垂直于前向量和世界上向量）
        world_up = np.array([0, 0, 1])  # Z轴向上
        camera_right = np.cross(camera_forward, world_up)
        camera_right = camera_right / np.linalg.norm(camera_right)
        
        # 获取摄像机上向量（垂直于前向量和右向量）
        camera_up = np.cross(camera_right, camera_forward)
        camera_up = camera_up / np.linalg.norm(camera_up)
        
        # 确定控制器轴的方向
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
        
        # 投影到控制轴方向
        drag_amount = np.dot(drag_dir, axis_dir) * sensitivity
        
        return drag_amount
    
    def _draw_transform_controller(self, geometry):
        """
        绘制变换控制器
        
        参数:
            geometry: 选中的几何体
        """
        operation_mode = self._scene_viewmodel.operation_mode
        
        # 保存当前矩阵
        glPushMatrix()
        
        # 根据坐标系选择决定变换控制器的位置和方向
        if self._use_local_coords:
            # 使用局部坐标系 - 使用物体的完整变换矩阵
            matrix = geometry.transform_matrix.T.flatten().tolist()
            glMultMatrixf(matrix)
        else:
            # 使用全局坐标系 - 只使用物体的位置，将旋转设为单位矩阵
            # 获取物体的变换矩阵
            transform_matrix = geometry.transform_matrix.copy()
            
            # 创建单位旋转矩阵
            rot_matrix = np.eye(3)
            
            # 替换变换矩阵中的旋转部分(前3x3)，保留平移部分
            transform_matrix[:3, :3] = rot_matrix
            
            # 将修改后的矩阵转置并展平为OpenGL所需的列优先格式
            matrix = transform_matrix.T.flatten().tolist()
            glMultMatrixf(matrix)
        
        # 设置混合模式，使控制器在几何体上方清晰可见
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        # 绘制坐标系指示器
        glDisable(GL_LIGHTING)
        
        # 绘制坐标系标志
        coord_label = "局部坐标系" if self._use_local_coords else "全局坐标系"
        self._draw_coordinate_label(coord_label)
        
        glEnable(GL_LIGHTING)
        
        # 绘制相应的控制器
        if operation_mode == OperationMode.TRANSLATE:
            self._draw_translation_gizmo()
        elif operation_mode == OperationMode.ROTATE:
            self._draw_rotation_gizmo()
        elif operation_mode == OperationMode.SCALE:
            self._draw_scale_gizmo()
        
        # 恢复矩阵
        glPopMatrix()

    def _draw_coordinate_label(self, label_text):
        """绘制坐标系标签"""
        # 该函数需要根据您的OpenGL文本渲染方式实现
        # 这里提供一个简单的示意
        
        # 设置2D正交投影
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width(), 0, self.height(), -1, 1)
        
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        
        # 绘制坐标系状态文本
        coord_color = (1.0, 1.0, 0.0) if self._use_local_coords else (0.0, 1.0, 1.0)
        glColor3f(*coord_color)
        
        # 在屏幕左下角显示坐标系状态
        # 具体的文本渲染需要根据您的实现方式调整
        # 这里只是一个示例占位
        
        # 恢复投影和模型视图矩阵
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

    def dragEnterEvent(self, event):
        """处理拖拽进入事件"""
        if event.mimeData().hasText():
            # 接受拖拽
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """处理拖拽移动事件"""
        if not event.mimeData().hasText():
            event.ignore()
            return
        
        try:
            # 获取几何体类型值
            geo_type_text = event.mimeData().text()
            print(f"拖拽类型: '{geo_type_text}'，类型: {type(geo_type_text)}")
            
            # 获取当前鼠标位置
            mouse_pos = event.pos()
            
            # 计算世界位置
            world_pos = self._get_position_at_mouse(mouse_pos)
            
            # 更新预览状态
            self.drag_preview = {
                'active': True,
                'position': world_pos,
                'type': geo_type_text
            }
            
            # 重绘界面
            self.update()
            
            # 接受拖拽
            event.acceptProposedAction()
        except Exception as e:
            print(f"拖拽移动处理出错: {e}")
            import traceback
            traceback.print_exc()
            event.ignore()

    def dragLeaveEvent(self, event):
        """处理拖拽离开事件"""
        # 清除预览
        self.drag_preview = {'active': False, 'position': None, 'type': None}
        self.update()
        event.accept()

    def dropEvent(self, event):
        """处理拖拽放置事件"""
        if not event.mimeData().hasText():
            event.ignore()
            return
        
        try:
            # 获取几何体类型值（字符串）
            geo_type_value = event.mimeData().text()
            
            # 获取放置位置
            mouse_pos = event.pos()
            world_pos = self._get_position_at_mouse(mouse_pos)
            
            # 创建几何体
            self._create_geometry_at_position(geo_type_value, world_pos)
            
            # 清除预览
            self.drag_preview = {'active': False, 'position': None, 'type': None}
            self.update()
            
            # 接受拖拽
            event.acceptProposedAction()
        except Exception as e:
            print(f"拖拽放置处理出错: {e}")
            event.ignore()

    def _get_position_at_mouse(self, mouse_pos):
        """
        获取鼠标位置对应的世界坐标
        
        参数:
            mouse_pos: 鼠标位置(QPoint)
            
        返回:
            世界坐标(numpy数组)
        """
        try:
            # 获取视口尺寸
            viewport_width = self.width()
            viewport_height = self.height()
            
            # 获取射线
            ray_origin, ray_direction = self._get_mouse_ray(mouse_pos.x(), mouse_pos.y(), viewport_width, viewport_height)
            
            # 使用场景视图模型的射线投射器检测与几何体的交点
            result = self._scene_viewmodel._raycaster.raycast(mouse_pos.x(), mouse_pos.y(), viewport_width, viewport_height)
            
            if result and result.is_hit():
                # 如果射线击中了几何体，使用击中点
                # RaycastResult 类使用 hit_point 而不是 hit_position
                if hasattr(result, 'hit_point'):
                    # 将位置稍微提高，避免与现有物体重叠
                    return result.hit_point + np.array([0.0, 0.2, 0.0])
                
                # 如果没有hit_point，可以尝试使用距离计算击中点
                if hasattr(result, 'distance'):
                    hit_point = ray_origin + ray_direction * result.distance
                    return hit_point + np.array([0.0, 0.2, 0.0])
                
                # 如果上述方法都失败，从几何体获取位置
                if hasattr(result, 'geometry') and hasattr(result.geometry, 'get_world_position'):
                    geometry_pos = result.geometry.get_world_position()
                    # 将位置稍微提高，避免与现有物体重叠
                    return geometry_pos + np.array([0.0, result.geometry.size[1] if hasattr(result.geometry, 'size') else 0.5, 0.0])
            
            # 如果没有击中几何体，计算与y=0平面的交点
            if ray_direction[1] != 0:
                t = -ray_origin[1] / ray_direction[1]
                if t > 0:
                    # 计算交点
                    intersection = ray_origin + t * ray_direction
                    return intersection
            
            # 默认返回原点
            return np.array([0.0, 0.0, 0.0])
        
        except Exception as e:
            print(f"获取鼠标位置出错: {e}")
            import traceback
            traceback.print_exc()
            # 发生错误时返回安全的默认值
            return np.array([0.0, 0.0, 0.0])

    def _get_mouse_ray(self, x, y, viewport_width, viewport_height):
        """
        获取从鼠标位置发射的射线
        
        参数:
            x, y: 鼠标坐标
            viewport_width, viewport_height: 视口尺寸
            
        返回:
            (ray_origin, ray_direction): 射线起点和方向
        """
        # 使用场景视图模型的坐标转换方法
        return self._scene_viewmodel.screen_to_world_ray(x, y, viewport_width, viewport_height)

    def _create_geometry_at_position(self, geo_type_value, position):
        """
        在指定位置创建几何体
        
        参数:
            geo_type_value: 几何体类型值（字符串）
            position: 位置坐标
        """
        try:
            # 将字符串值转换为GeometryType枚举
            geo_type = None
            
            # 遍历所有几何体类型，找到匹配的值
            for gt in GeometryType:
                if gt.value == geo_type_value:
                    geo_type = gt
                    break
            
            # 如果没有找到匹配的枚举值，打印错误并返回
            if geo_type is None:
                print(f"错误：无效的几何体类型值 '{geo_type_value}'")
                print(f"有效的几何体类型值: {[gt.value for gt in GeometryType]}")
                return
            
            # 为不同几何体类型设置默认尺寸
            default_sizes = {
                GeometryType.BOX: (0.5, 0.5, 0.5),
                GeometryType.SPHERE: (0.5, 0.5, 0.5),
                GeometryType.CYLINDER: (0.5, 0.5, 0.5),
                GeometryType.PLANE: (1.0, 0.01, 1.0),
                GeometryType.CAPSULE: (0.5, 0.5, 0.5),
                GeometryType.ELLIPSOID: (0.5, 0.3, 0.5)
            }
            
            # 创建几何体
            geometry = self._scene_viewmodel.create_geometry(
                geo_type=geo_type,
                position=tuple(position),
                size=default_sizes.get(geo_type, (0.5, 0.5, 0.5))
            )
            
            # 选中新创建的几何体
            if geometry:
                self._scene_viewmodel.selected_geometry = geometry
                
                # 如果当前是观察模式，切换到平移模式
                if self._scene_viewmodel.operation_mode == OperationMode.OBSERVE:
                    self._scene_viewmodel.operation_mode = OperationMode.TRANSLATE
        
        except Exception as e:
            print(f"创建几何体出错: {e}")
            import traceback
            traceback.print_exc()

    def _draw_drag_preview(self):
        """绘制拖拽预览"""
        if not self.drag_preview['active'] or self.drag_preview['position'] is None:
            return
        
        position = self.drag_preview['position']
        geo_type_value = self.drag_preview['type']
        
        try:
            # 转换为GeometryType枚举
            geo_type = None
            
            # 遍历所有几何体类型，找到匹配的值
            for gt in GeometryType:
                if gt.value == geo_type_value:
                    geo_type = gt
                    break
            
            # 如果没有找到匹配的枚举值，返回
            if geo_type is None:
                print(f"预览错误：无效的几何体类型值 '{geo_type_value}'")
                return
            
            # 保存当前状态
            glPushMatrix()
            
            # 半透明蓝色
            glColor4f(0.2, 0.5, 1.0, 0.5)
            
            # 移动到预览位置
            glTranslatef(position[0], position[1], position[2])
            
            # 为不同几何体类型设置默认尺寸
            default_sizes = {
                GeometryType.BOX: (0.5, 0.5, 0.5),
                GeometryType.SPHERE: (0.5, 0.5, 0.5),
                GeometryType.CYLINDER: (0.5, 0.5, 0.5),
                GeometryType.PLANE: (1.0, 0.01, 1.0),
                GeometryType.CAPSULE: (0.5, 0.5, 0.5),
                GeometryType.ELLIPSOID: (0.5, 0.3, 0.5)
            }
            
            # 获取默认尺寸
            size = default_sizes.get(geo_type, (0.5, 0.5, 0.5))
            
            # 根据几何体类型绘制
            if geo_type == GeometryType.BOX:
                self._draw_box(size[0], size[1], size[2])
            elif geo_type == GeometryType.SPHERE:
                self._draw_sphere(size[0])
            elif geo_type == GeometryType.CYLINDER:
                self._draw_cylinder(size[0], size[2])
            elif geo_type == GeometryType.CAPSULE:
                self._draw_capsule(size[0], size[1])
            elif geo_type == GeometryType.PLANE:
                self._draw_plane()
            elif geo_type == GeometryType.ELLIPSOID:
                self._draw_ellipsoid(size[0], size[1], size[2])
            
            # 恢复状态
            glPopMatrix()
        except Exception as e:
            print(f"绘制预览出错: {e}")
            import traceback
            traceback.print_exc() 

    def _draw_hollow_cylinder(self, radius, thickness, slices, axis="z"):
        """
        绘制中空的圆柱体（环状）
        
        参数:
            radius: 环的半径
            thickness: 环的厚度（高度）
            slices: 细分数
            axis: 环的朝向轴("x", "y", "z")
        """
        import math
        
        inner_radius = radius * 0.8  # 内径为外径的80%
        half_thickness = thickness / 2.0
        
        # 确定圆环的旋转
        if axis == "x":
            # 使圆环法线朝向X轴
            glRotatef(90, 0, 1, 0)
        elif axis == "y":
            # 使圆环法线朝向Y轴
            glRotatef(90, 1, 0, 0)
        # Z轴不需要额外旋转
        
        # 使用 GL_TRIANGLES 绘制，将圆环分解为三角形
        # 外圆柱面
        glBegin(GL_TRIANGLE_STRIP)
        for i in range(slices + 1):
            angle = 2.0 * math.pi * i / slices
            cos_val = math.cos(angle)
            sin_val = math.sin(angle)
            
            # 外圆柱体底部顶点
            glVertex3f(radius * cos_val, radius * sin_val, -half_thickness)
            # 外圆柱体顶部顶点
            glVertex3f(radius * cos_val, radius * sin_val, half_thickness)
        glEnd()
        
        # 内圆柱面
        glBegin(GL_TRIANGLE_STRIP)
        for i in range(slices + 1):
            angle = 2.0 * math.pi * i / slices
            cos_val = math.cos(angle)
            sin_val = math.sin(angle)
            
            # 内圆柱体顶部顶点
            glVertex3f(inner_radius * cos_val, inner_radius * sin_val, half_thickness)
            # 内圆柱体底部顶点
            glVertex3f(inner_radius * cos_val, inner_radius * sin_val, -half_thickness)
        glEnd()
        
        # 顶面（连接内外圆）
        glBegin(GL_TRIANGLE_STRIP)
        for i in range(slices + 1):
            angle = 2.0 * math.pi * i / slices
            cos_val = math.cos(angle)
            sin_val = math.sin(angle)
            
            # 内圆顶点
            glVertex3f(inner_radius * cos_val, inner_radius * sin_val, half_thickness)
            # 外圆顶点
            glVertex3f(radius * cos_val, radius * sin_val, half_thickness)
        glEnd()
        
        # 底面（连接内外圆）
        glBegin(GL_TRIANGLE_STRIP)
        for i in range(slices + 1):
            angle = 2.0 * math.pi * i / slices
            cos_val = math.cos(angle)
            sin_val = math.sin(angle)
            
            # 外圆顶点
            glVertex3f(radius * cos_val, radius * sin_val, -half_thickness)
            # 内圆顶点
            glVertex3f(inner_radius * cos_val, inner_radius * sin_val, -half_thickness)
        glEnd()

    def _get_world_matrix(self, geometry):
        """
        计算对象的世界变换矩阵（考虑所有父对象的变换）
        
        参数:
            geometry: 几何体对象
            
        返回:
            4x4 世界变换矩阵
        """
        # 如果对象没有父对象，直接返回其变换矩阵
        return geometry.transform_matrix.copy()
        


    def _world_to_local_matrix(self, world_matrix, geometry):
        """
        将世界变换矩阵转换为局部变换矩阵
        
        参数:
            world_matrix: 4x4 世界变换矩阵
            geometry: 几何体对象
            
        返回:
            4x4 局部变换矩阵
        """
        # 如果对象没有父对象，世界矩阵即为局部矩阵
        if not hasattr(geometry, 'parent') or geometry.parent is None:
            return world_matrix.copy()
        
        # 获取父对象的世界变换矩阵
        parent_world_matrix = self._get_world_matrix(geometry.parent)
        
        # 计算父对象世界变换矩阵的逆
        parent_world_matrix_inv = np.linalg.inv(parent_world_matrix)
        
        # 应用父对象逆变换，将世界矩阵转换为局部矩阵
        return parent_world_matrix_inv @ world_matrix

    def _decompose_matrix(self, matrix):
        """
        将4x4变换矩阵分解为位置、旋转和缩放
        
        参数:
            matrix: 4x4变换矩阵
            
        返回:
            (position, rotation, scale): 分解后的位置、旋转（欧拉角）和缩放
        """
        # 提取位置
        position = matrix[:3, 3]
        
        # 提取旋转矩阵
        rotation_matrix = matrix[:3, :3]
        
        # 提取缩放（列向量的长度）
        scale = np.array([
            np.linalg.norm(rotation_matrix[:, 0]),
            np.linalg.norm(rotation_matrix[:, 1]),
            np.linalg.norm(rotation_matrix[:, 2])
        ])
        
        # 归一化旋转矩阵（移除缩放）
        rotation_matrix_normalized = np.column_stack([
            rotation_matrix[:, 0] / scale[0],
            rotation_matrix[:, 1] / scale[1],
            rotation_matrix[:, 2] / scale[2]
        ])
        
        # 从归一化旋转矩阵计算欧拉角
        rotation = self._matrix_to_euler_angles(rotation_matrix_normalized)
        
        return position, rotation, scale

    def _matrix_to_euler_angles(self, rotation_matrix):
        """
        将3x3旋转矩阵转换为欧拉角（XYZ顺序，度数）
        
        参数:
            rotation_matrix: 3x3旋转矩阵
            
        返回:
            np.array([rx, ry, rz]): 欧拉角（度数）- XYZ顺序
        """
        # 从旋转矩阵中提取欧拉角 - XYZ顺序
        # 说明: 先绕X轴，再绕Y轴，最后绕Z轴
        
        # 处理万向节锁的情况
        if abs(rotation_matrix[0, 2]) >= 1.0 - 1e-6:
            # 万向节锁
            sign = -1 if rotation_matrix[0, 2] < 0 else 1
            x = 0
            y = sign * np.pi/2
            z = sign * np.arctan2(-rotation_matrix[1, 0], rotation_matrix[1, 1])
        else:
            y = np.arcsin(rotation_matrix[0, 2])
            cos_y = np.cos(y)
            x = np.arctan2(-rotation_matrix[1, 2] / cos_y, rotation_matrix[2, 2] / cos_y)
            z = np.arctan2(-rotation_matrix[0, 1] / cos_y, rotation_matrix[0, 0] / cos_y)
        
        # 转换为度数
        return np.array([np.degrees(x), np.degrees(y), np.degrees(z)])

    # 创建绕各轴旋转的矩阵函数
    def _create_rotation_matrix_x(self, angle_rad):
        """创建绕X轴旋转的4x4矩阵"""
        matrix = np.eye(4)
        c, s = np.cos(angle_rad), np.sin(angle_rad)
        matrix[1:3, 1:3] = np.array([[c, -s], [s, c]])
        return matrix

    def _create_rotation_matrix_y(self, angle_rad):
        """创建绕Y轴旋转的4x4矩阵"""
        matrix = np.eye(4)
        c, s = np.cos(angle_rad), np.sin(angle_rad)
        matrix[0, 0] = c
        matrix[0, 2] = s
        matrix[2, 0] = -s
        matrix[2, 2] = c
        return matrix

    def _create_rotation_matrix_z(self, angle_rad):
        """创建绕Z轴旋转的4x4矩阵"""
        matrix = np.eye(4)
        c, s = np.cos(angle_rad), np.sin(angle_rad)
        matrix[0, 0] = c
        matrix[0, 1] = -s
        matrix[1, 0] = s
        matrix[1, 1] = c
        return matrix

    def _on_coordinate_system_changed(self, use_local_coords):
        """处理坐标系模式变化"""
        self._use_local_coords = use_local_coords
        # 更新控制器
        self._update_controllor_raycaster()
        # 重绘场景
        self.update()
        
        # 在状态栏显示当前坐标系模式
        parent_window = self.window()
        if hasattr(parent_window, 'statusBar'):
            coord_system = "局部坐标系" if self._use_local_coords else "全局坐标系"
            parent_window.statusBar().showMessage(f"当前模式: {coord_system}", 2000)