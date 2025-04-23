# MuJoCo 场景编辑器

这是一个基于PyQt5开发的图形界面编辑器，专门用于创建和编辑MuJoCo场景描述语言（MJCF）文件。

## 功能特点

- 可视化创建和编辑MuJoCo场景
- 支持基本几何体（盒子、球体、圆柱体、胶囊体、平面等）
- 层级结构管理
- 属性编辑面板
- 导入/导出MuJoCo XML格式

## 安装

### 依赖

- Python >= 3.7
- PyQt5 >= 5.15.0
- NumPy >= 1.20.0
- PyOpenGL >= 3.1.0

### 安装步骤

1. 克隆仓库：
   ```
   git clone https://github.com/yourusername/xml-editor.git
   cd xml-editor
   ```

2. 安装依赖：
   ```
   pip install .
   ```

或者开发模式安装：
   ```
   pip install -e .
   ```

## 使用方法

运行主程序：

```
python -m xml_editor.main
```

### 基本操作

- **添加几何体**：使用控制面板中的按钮添加各种几何体
- **选择对象**：点击场景中的对象进行选择
- **变换对象**：使用工具栏中的平移、旋转、缩放工具
- **属性编辑**：在右侧属性面板中编辑选中对象的属性
- **层级管理**：在左侧层级树中管理对象的层级结构
- **保存/打开**：使用文件菜单保存或打开MJCF场景

## 架构

项目采用MVVM（Model-View-ViewModel）架构：

- **Model**：数据模型，处理MJCF场景数据的加载、保存和内部表示
- **View**：视图层，包括OpenGL渲染窗口和各种UI组件
- **ViewModel**：视图模型，作为视图和模型之间的桥梁

## 许可

MIT License 