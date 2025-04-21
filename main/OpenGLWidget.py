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
from Geomentry import TriangleGeometry  # 使用正确的模块名

class GeometryType(OriginalGeometryType):
    if not hasattr(OriginalGeometryType, 'ELLIPSOID'):
        ELLIPSOID = 'ellipsoid'
    if not hasattr(OriginalGeometryType, 'TRIANGLE'):
        TRIANGLE = 'triangle'

if not hasattr(GeometryType, 'ELLIPSOID'):
    setattr(GeometryType, 'ELLIPSOID', 'ellipsoid')
if not hasattr(GeometryType, 'TRIANGLE'):
    setattr(GeometryType, 'TRIANGLE', 'triangle')

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
        self.last_mouse_pos = QPoint(0, 0)  # 使用默认位置初始化，而不是None
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
        
        # 添加旋转控件相关的属性
        self.rotation_axis = None  # 当前选中的旋转轴
        
        # 添加网格显示控制变量
        self.show_grid = True
        self.grid_color = (1.0, 1.0, 1.0, 1.0)  # 默认白色网格颜色

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
            # 绘制胶囊体 - 符合MuJoCo标准，以Z轴为主轴，中心位于圆柱体中心
            radius = geo.size[0]
            half_height = geo.size[1]
            
            # 创建二次曲面对象
            quad = gluNewQuadric()
            
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



    def mousePressEvent(self, event):
        """处理鼠标按下事件"""
        # 记录初始鼠标位置
        self.last_mouse_pos = event.pos()
        
        if event.button() == Qt.LeftButton:
            # 确保正确初始化鼠标位置
            self.drag_start_pos = event.pos()
            self.left_button_pressed = True
            
            # 检查是否有物体被点击
            try:
                # 首先检查是否点击了变换轴或悬浮坐标系（仅当已有选中物体时）
                if self.selected_geo:
                    # 检查悬浮坐标系
                    # self.active_axis = self.detect_floating_axis(event.pos())
                    # if self.active_axis:
                    #     self._dragging_floating_gizmo = True
                    #     self.dragging = True
                    #     return
                        
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
        """处理鼠标移动事件"""
        # 检查last_mouse_pos是否已初始化
        if self.last_mouse_pos is None:
            self.last_mouse_pos = event.pos()
            return
        
        # 计算鼠标移动的距离
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
            self.smooth_focus_on_object(self.selected_geo)
            
        elif event.button() == Qt.RightButton:
            self.right_button_pressed = False
        
        # 释放鼠标后不执行任何额外操作
        
        # 在鼠标松开时重置 last_mouse 位置
        self.last_mouse_pos = None
        # 或者如果您使用的变量名是 last_mouse
        # self.last_mouse = None
        
        # 重置其他可能需要清理的拖拽状态变量
        self.dragging = False
        if hasattr(self, 'drag_start_pos'):
            self.drag_start_pos = None
        
        self.update()  # 确保视图更新

    def handle_view_pan(self, dx, dy):
        """视角平移 - 在任意相机角度正确工作
        
        优化版本：
        1. 正确处理任意相机视角
        2. 平移限制在屏幕平面内
        3. 动态调整平移速度
        """
        # 更新相机向量，确保在计算前有最新的向量
        self.update_camera_vectors()
        
        # 获取相机位置和目标点
        camera_position = self.camera_config['position']
        
        # 计算平移缩放因子 - 基于当前视角距离
        distance = np.linalg.norm(camera_position - self._camera_target)
        base_factor = 0.003  # 降低基础系数以获得更精细的控制
        scale_factor = base_factor * distance
        
        # 如果移动距离太小，则不处理
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            return
        
        # 使用相机的right和up向量 - 这些向量定义了与视线垂直的平面
        # 无论相机如何旋转，这些向量总是与屏幕平面对齐
        right_offset = self.camera_right * (-dx * scale_factor)
        up_offset = self.camera_up * (dy * scale_factor)
        
        # 合并为一个平移向量
        pan_vector = right_offset + up_offset
        
        # 同时移动相机位置和目标点，保持视线方向不变
        self._camera_target += pan_vector
        self.camera_config['position'] += pan_vector
        
        # 更新相机配置
        self.update_camera_config()
        
        # 确保视图更新
        self.update()

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
            self.smooth_focus_on_object(geo)

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
                    self.smooth_focus_on_object(geo)
        
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
        # 如果不显示网格，则直接返回
        if not self.show_grid:
            return
        
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
        
        # 禁用光照以防止材质影响网格颜色
        glDisable(GL_LIGHTING)
        
        # 主网格线 - 使用设置的网格颜色
        glColor4f(
            self.grid_color[0], 
            self.grid_color[1], 
            self.grid_color[2], 
            0.3 # 保持透明度为固定值，以确保网格不会过于明显
        )
        self._draw_grid_lines(center_x, center_z, main_interval, main_extent)
        
        # 次网格线 - 使用更暗的网格颜色
        darker_color = (
            self.grid_color[0] ,  # 使颜色更暗
            self.grid_color[1] ,
            self.grid_color[2] ,
            0.15  # 更低的透明度
        )
        glColor4f(*darker_color)
        self._draw_grid_lines(center_x, center_z, main_interval/5, main_extent)
        
        # 恢复原始颜色和状态
        glColor4fv(current_color)
        
        # 如果原先启用了光照，重新启用
        glEnable(GL_LIGHTING)

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
        """绘制无限延伸的世界坐标轴"""
        # 保存当前属性
        glPushAttrib(GL_ENABLE_BIT | GL_LINE_BIT)
        
        try:
            # 禁用光照，以便坐标轴颜色更清晰
            glDisable(GL_LIGHTING)
            glDisable(GL_TEXTURE_2D)
            
            # 设置线宽
            glLineWidth(2.0)
            
            # 绘制X轴（红色）
            glBegin(GL_LINES)
            glColor3f(1.0, 0.0, 0.0)  # 红色
            glVertex3f(-1000.0, 0.0, 0.0)
            glVertex3f(1000.0, 0.0, 0.0)
            glEnd()
            
            # 绘制Y轴（绿色）
            glBegin(GL_LINES)
            glColor3f(0.0, 1.0, 0.0)  # 绿色
            glVertex3f(0.0, -1000.0, 0.0)
            glVertex3f(0.0, 1000.0, 0.0)
            glEnd()
            
            # 绘制Z轴（蓝色）
            glBegin(GL_LINES)
            glColor3f(0.0, 0.0, 1.0)  # 蓝色
            glVertex3f(0.0, 0.0, -1000.0)
            glVertex3f(0.0, 0.0, 1000.0)
            glEnd()
        
        finally:
            # 确保无论如何都会恢复状态
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

        print(dx)
        
        # 根据活动轴应用平移
        if self.active_axis == 'x':
            # 在X轴方向平移
            self.selected_geo.position[0] -= dx * scale_factor
        elif self.active_axis == 'y':
            # 在Y轴方向平移
            self.selected_geo.position[1] += dx * scale_factor
        elif self.active_axis == 'z':
            # 在Z轴方向平移
            self.selected_geo.position[2] -= dy * scale_factor
        
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
            # 将字符串的 active_axis 转换为数值索引
            if isinstance(self.active_axis, str):
                axis_map = {'x': 0, 'y': 1, 'z': 2, 'xyz': 3}
                axis_index = axis_map.get(self.active_axis.lower(), -1)
            else:
                axis_index = self.active_axis
            
            # 确定缩放因子
            scale_factor = 1.0
            scale_direction = [0, 0, 0]
            
            if axis_index < 3:  # 单轴缩放
                axis_vector = axis_vectors[axis_index]
                
                # 计算视图与轴之间的点积，决定正负方向
                view_dot = np.dot(view_dir, axis_vector)
                
                # 计算有效拖动量
                if axis_index == 2:
                    drag_amount = -dy * 0.01  # 垂直拖动，上移增大
                else:
                    # 确定水平拖动方向（右移增大还是左移增大）
                    drag_amount = dx * 0.01 * (1 if view_dot < 0 else -1)
                
                # 计算缩放因子
                scale_factor = 1.0 + drag_amount
                scale_direction[axis_index] = 1
                
            elif axis_index == 3:  # 均匀缩放（中心控件）
                # 对于均匀缩放，使用水平和垂直拖动的平均值
                drag_amount = (dx + dy) * 0.005
                
                # 计算缩放因子
                scale_factor = 1.0 + drag_amount
                scale_direction = [1, 1, 1]  # 所有方向都缩放
            
            # 检查缩放因子是否有效
            if not np.isfinite(scale_factor) or abs(scale_factor) < 0.0001:
                print(f"警告: 缩放因子无效 ({scale_factor})，跳过缩放操作")
                return
            
            # 检查是否是组对象
            if hasattr(self.selected_geo, 'type') and self.selected_geo.type == "group":
                # 使用 _scale_group_recursive 进行组缩放
                self._scale_group_recursive(
                    self.selected_geo, 
                    self.selected_geo.position, 
                    scale_factor, 
                    scale_direction
                )
                
                # 更新组的变换矩阵（如果有）
                if hasattr(self.selected_geo, '_update_transform'):
                    self.selected_geo._update_transform()
                if hasattr(self.selected_geo, '_update_children_transforms'):
                    self.selected_geo._update_children_transforms()
            else:
                # 普通物体的缩放处理
                current_size = list(self.selected_geo.size)
                
                # 根据缩放方向应用缩放
                for i in range(3):
                    if scale_direction[i]:
                        # 应用缩放因子到尺寸
                        if axis_index < 3:  # 单轴缩放
                            # 直接增加/减少
                            current_size[i] += drag_amount
                        else:  # 均匀缩放
                            # 使用乘法缩放
                            current_size[i] *= scale_factor
                        
                        # 确保尺寸不会太小
                        current_size[i] = max(0.1, current_size[i])
                
                # 应用新的尺寸
                self.selected_geo.size = current_size
        
        except Exception as e:
            print(f"缩放拖拽出错: {str(e)}")
            import traceback
            traceback.print_exc()

    
    



    
    
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


        self.drag_preview = {'active': False}

        self.update()
        
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
            
        glClear(GL_DEPTH_BUFFER_BIT) 
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
        """绘制不与物体重合的旋转控件，使用三个首尾相连的圆柱体构成三角形"""
        if not self.selected_geo:
            return
            
        # 计算物体的世界坐标位置和尺寸
        obj_pos = self.selected_geo.position
        obj_size = np.max(self.selected_geo.size)
        
        # 确定控件的位置 - 距离物体一定距离
        camera_pos = self.camera_config['position']
        
        # 更新相机向量
        self.update_camera_vectors()
        
        # 使用相机的右向量确定控件位置
        offset_distance = max(obj_size * 2.5, 1.0)
        gizmo_pos = obj_pos + self.camera_right * offset_distance + np.array([0, 0, offset_distance * 0.5])
        
        if self.selected_geo.type == GeometryType.PLANE:
            gizmo_pos = obj_pos + np.array([0, 0, offset_distance])
        
        # 控件参数
        axis_length = max(1.5, obj_size * 0.6)  # 三角形边长
        axis_thickness = axis_length * 0.05    # 圆柱体半径
        
        # 存储几何信息用于检测
        self.rotation_gizmo_geometries = []
        
        # 定义三角形的三个顶点
        p1 = np.array([axis_length, 0, 0])     # X轴方向点
        p2 = np.array([0, axis_length, 0])     # Y轴方向点
        p3 = np.array([0, 0, axis_length])     # Z轴方向点
        
        # 绘制坐标系原点（小球）
        glPushMatrix()
        glTranslatef(*gizmo_pos)
        
        # 禁用深度测试和光照以便更清晰地显示控件
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        
        # 原点球
        glColor3f(0.8, 0.8, 0.8)
        glutSolidSphere(axis_thickness * 1.5, 12, 12)
        
        # X轴旋转控件 - 红色 (从p2到p3)
        glColor4f(1.0, 0.0, 0.0, 0.8)  # 红色
        if hasattr(self, 'rotation_axis') and self.rotation_axis == 'x':
            glColor4f(1.0, 1.0, 0.0, 0.8)  # 高亮为黄色
        
        self._draw_cylinder(p2[0], p2[1], p2[2], p3[0], p3[1], p3[2], axis_thickness)
        
        # 保存X轴几何信息
        x_cylinder = Geometry(geo_type=GeometryType.CYLINDER)  # 修复：提供geo_type参数
        x_cylinder.name = "rotation_x_axis"
        x_cylinder.position = (p2 + p3) / 2
        x_cylinder.size = np.array([axis_thickness, np.linalg.norm(p3 - p2) / 2, axis_thickness])
        x_cylinder.material.color = [1.0, 0.0, 0.0, 0.8]
        self.rotation_gizmo_geometries.append(('x', x_cylinder))
        
        # Y轴旋转控件 - 绿色 (从p3到p1)
        glColor4f(0.0, 1.0, 0.0, 0.8)  # 绿色
        if hasattr(self, 'rotation_axis') and self.rotation_axis == 'y':
            glColor4f(1.0, 1.0, 0.0, 0.8)  # 高亮为黄色
        
        self._draw_cylinder(p3[0], p3[1], p3[2], p1[0], p1[1], p1[2], axis_thickness)
        
        # 保存Y轴几何信息
        y_cylinder = Geometry(geo_type=GeometryType.CYLINDER)  # 修复：提供geo_type参数
        y_cylinder.name = "rotation_y_axis"
        y_cylinder.position = (p3 + p1) / 2
        y_cylinder.size = np.array([axis_thickness, np.linalg.norm(p1 - p3) / 2, axis_thickness])
        y_cylinder.material.color = [0.0, 1.0, 0.0, 0.8]
        self.rotation_gizmo_geometries.append(('y', y_cylinder))
        
        # Z轴旋转控件 - 蓝色 (从p1到p2)
        glColor4f(0.0, 0.0, 1.0, 0.8)  # 蓝色
        if hasattr(self, 'rotation_axis') and self.rotation_axis == 'z':
            glColor4f(1.0, 1.0, 0.0, 0.8)  # 高亮为黄色
        
        self._draw_cylinder(p1[0], p1[1], p1[2], p2[0], p2[1], p2[2], axis_thickness)
        
        # 保存Z轴几何信息
        z_cylinder = Geometry(geo_type=GeometryType.CYLINDER)  # 修复：提供geo_type参数
        z_cylinder.name = "rotation_z_axis"
        z_cylinder.position = (p1 + p2) / 2
        z_cylinder.size = np.array([axis_thickness, np.linalg.norm(p2 - p1) / 2, axis_thickness])
        z_cylinder.material.color = [0.0, 0.0, 1.0, 0.8]
        self.rotation_gizmo_geometries.append(('z', z_cylinder))
        
        # 恢复OpenGL状态
        glEnable(GL_LIGHTING)
        glEnable(GL_DEPTH_TEST)
        glPopMatrix()
        
        # 存储控件位置信息供检测使用
        self.rotation_gizmo_pos = gizmo_pos

    def _draw_cylinder(self, x1, y1, z1, x2, y2, z2, radius, slices=8):
        """
        绘制一个圆柱体，从点(x1,y1,z1)到点(x2,y2,z2)
        """
        direction = np.array([x2-x1, y2-y1, z2-z1])
        length = np.linalg.norm(direction)
        
        if length < 1e-6:
            return  # 避免长度为零的情况
        
        # 标准化方向向量
        direction = direction / length
        
        # 计算两个互相垂直且都垂直于direction的向量
        v = np.array([0.0, 1.0, 0.0])  # 辅助向量
        if abs(np.dot(v, direction)) > 0.9:
            v = np.array([1.0, 0.0, 0.0])
        
        # 第一个垂直向量
        u1 = np.cross(v, direction)
        u1 = u1 / np.linalg.norm(u1)
        
        # 第二个垂直向量
        u2 = np.cross(direction, u1)
        
        # 绘制圆柱体的侧面
        glBegin(GL_QUAD_STRIP)
        for i in range(slices+1):
            angle = 2.0 * np.pi * i / slices
            c = np.cos(angle)
            s = np.sin(angle)
            
            # 圆柱体底部顶点
            normal = c * u1 + s * u2
            glNormal3f(*normal)
            glVertex3f(x1 + radius * normal[0], y1 + radius * normal[1], z1 + radius * normal[2])
            
            # 圆柱体顶部顶点
            glVertex3f(x2 + radius * normal[0], y2 + radius * normal[1], z2 + radius * normal[2])
        glEnd()

    def _detect_rotation_axis(self, mouse_pos, position):
        """使用Raycaster检测旋转控件的点击"""
        if not hasattr(self, 'rotation_gizmo_geometries') or not self.rotation_gizmo_geometries:
            return None
    
        try:
            # 创建临时射线投射器
            temp_raycaster = GeometryRaycaster(
                camera_config=self.camera_config,
                geometries=[geo for _, geo in self.rotation_gizmo_geometries]
            )
            
            # 为几何体临时增大碰撞范围
            original_sizes = {}
            for axis_name, geo in self.rotation_gizmo_geometries:
                # 保存原始大小
                original_sizes[axis_name] = geo.size.copy()
                # 临时将大小增加到1.5倍以便更容易选择
                geo.size = geo.size * 1.5
                # 暂时更新位置到世界坐标
                geo.position = self.rotation_gizmo_pos + geo.position
            
            # 投射射线检测碰撞
            result = temp_raycaster.cast_ray((mouse_pos.x(), mouse_pos.y()))
            
            # 恢复原始大小和位置
            for axis_name, geo in self.rotation_gizmo_geometries:
                geo.size = original_sizes[axis_name]
                geo.position = geo.position - self.rotation_gizmo_pos
            
            if result and result.geometry:
                # 找到对应的轴名称
                for axis_name, geo in self.rotation_gizmo_geometries:
                    if result.geometry == geo:
                        return axis_name
            
            return None
        
        except Exception as e:
            print(f"检测旋转控件出错: {str(e)}")
            return None



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
                axis = self._detect_rotation_axis(mouse_pos, self.selected_geo.position)
                if axis:
                    self.set_rotation_axis(axis)  # 设置当前旋转轴
                return axis
                
            return -1
        except Exception as e:
            print(f"轴检测出错: {str(e)}")
            return -1

  

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
            camera_target = np.array(self._camera_target)
            
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
            
            # 计算缩放因子和方向
            scale_factor = 1.0 + drag_amount
            axis_index = {'x': 0, 'y': 1, 'z': 2}[axis_name]
            scale_direction = [0, 0, 0]
            scale_direction[axis_index] = 1
            
            # 检查是否是组对象
            if hasattr(self.selected_geo, 'type') and self.selected_geo.type == "group":
                # 确保缩放因子有效
                if np.isfinite(scale_factor) and abs(scale_factor) > 0.0001:
                    # 调用组的递归缩放函数
                    self._scale_group_recursive(
                        self.selected_geo, 
                        self.selected_geo.position,
                        scale_factor, 
                        scale_direction
                    )
                    
                    # 更新组的变换
                    if hasattr(self.selected_geo, '_update_transform'):
                        self.selected_geo._update_transform()
                    if hasattr(self.selected_geo, '_update_children_transforms'):
                        self.selected_geo._update_children_transforms()
            else:
                # 普通物体的缩放处理
                current_size = list(self.selected_geo.size)
                
                # 根据轴更新相应维度的尺寸
                current_size[axis_index] += drag_amount
                
                # 确保尺寸不会太小
                current_size[axis_index] = max(0.1, current_size[axis_index])
                
                # 应用新的尺寸
                self.selected_geo.size = current_size
                
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

    def set_rotation_axis(self, axis_name):
        """设置当前活动的旋转轴
        
        Args:
            axis_name: 轴名称 ('x', 'y', 'z' 或 None)
        """
        self.rotation_axis = axis_name
        self.update()  # 触发重绘，更新高亮显示

    # 添加新的平滑过渡方法
    def smooth_focus_on_object(self, geo):
        """平滑地将相机焦点移动到物体位置"""
        if not geo:
            return
            
        # 获取物体的位置作为目标点
        target_position = geo.position.copy()
        
        # 如果没有动画定时器，创建一个
        if not hasattr(self, 'animation_timer'):
            from PyQt5.QtCore import QTimer
            self.animation_timer = QTimer()
            self.animation_timer.timeout.connect(self._animation_step)
        
        # 停止当前可能正在运行的动画
        if self.animation_timer.isActive():
            self.animation_timer.stop()
        
        # 保存动画初始状态和参数
        import time
        self.animation_start_time = time.time()
        self.animation_duration = 0.3  # 动画持续时间，秒
        self.animation_start_target = self._camera_target.copy()
        self.animation_end_target = target_position.copy()
        
        # 启动动画
        self.animation_timer.start(16)  # 约60fps

    def _animation_step(self):
        """动画步骤回调函数"""
        import time
        current_time = time.time()
        elapsed = current_time - self.animation_start_time
        
        if elapsed >= self.animation_duration:
            # 动画结束
            self._camera_target = self.animation_end_target.copy()
            self.animation_timer.stop()
        else:
            # 计算动画进度
            t = elapsed / self.animation_duration
            # 使用缓入缓出函数
            t = self._ease_in_out_quad(t)
            
            # 插值计算当前相机目标位置
            self._camera_target = (
                self.animation_start_target * (1 - t) + 
                self.animation_end_target * t
            )
        
        # 更新相机配置和视图
        self.update_camera_config()
        self.update()

    def _ease_in_out_quad(self, t):
        """缓入缓出的二次方缓动函数"""
        if t < 0.5:
            return 2 * t * t
        else:
            return -1 + (4 - 2 * t) * t

    def _scale_group_recursive(self, group, center, scale_factor, scale_direction):
        """递归缩放组及其内部所有物体的局部坐标和尺寸
        
        Args:
            group: 要缩放的组
            center: 缩放的参考中心点
            scale_factor: 缩放因子
            scale_direction: 缩放方向 [x_scale, y_scale, z_scale]，值为1表示该方向缩放
        """
        # 健壮性检查
        if not hasattr(group, 'children') or not group.children:
            return
            
        # 验证缩放因子
        if not np.isfinite(scale_factor) or abs(scale_factor) < 0.0001:
            print(f"警告: 缩放因子无效 ({scale_factor})，跳过缩放操作")
            return
        
        # 确保缩放方向有效
        if not isinstance(scale_direction, list) or len(scale_direction) != 3:
            print(f"警告: 缩放方向无效 ({scale_direction})，跳过缩放操作")
            return
        
        # 遍历组内所有子物体
        for child in group.children:
            # 验证child和center有效性
            if child is None or center is None:
                continue
                
            try:
                # 计算子物体相对于组中心的偏移向量（局部坐标）
                local_offset = child.position - center
                
                # 对局部坐标应用缩放
                new_position = center.copy()  # 从中心点开始
                for i in range(3):
                    if scale_direction[i]:  # 如果该方向需要缩放
                        # 在该方向上应用缩放因子，检查有效性
                        offset_value = local_offset[i] * scale_factor
                        if np.isfinite(offset_value):  # 确保结果是有限值
                            new_position[i] += offset_value
                        else:
                            new_position[i] += local_offset[i]  # 使用原始偏移
                    else:
                        # 不缩放的方向保持原样
                        new_position[i] += local_offset[i]
                
                # 确保新位置有效
                if np.all(np.isfinite(new_position)):
                    # 更新子物体位置（局部坐标）
                    child.position = new_position
                
                # 根据子物体类型处理
                if hasattr(child, 'type') and child.type == "group":
                    # 如果子物体是组，递归处理其子物体
                    # 注意：使用子组自身的位置作为新的缩放中心点
                    self._scale_group_recursive(child, child.position, scale_factor, scale_direction)
                else:
                    # 如果是普通物体，缩放其尺寸
                    for i in range(3):
                        if scale_direction[i]:  # 如果该方向需要缩放
                            # 确保尺寸和缩放因子有效
                            if hasattr(child, 'size') and np.isfinite(scale_factor):
                                new_size = child.size[i] * scale_factor
                                if np.isfinite(new_size):  # 确保结果是有限值
                                    child.size[i] = max(0.1, new_size)  # 确保尺寸不会太小
            except Exception as e:
                print(f"缩放子物体时出错: {str(e)}")
                # 继续处理下一个子物体，不中断整个过程