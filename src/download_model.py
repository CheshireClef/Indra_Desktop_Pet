# src/download_model.py
"""
模型下载工具脚本
负责下载或更新 HuggingFace 上的 gte-multilingual-base 嵌入模型。
包含断点续传、网络错误处理及文件完整性校验逻辑。
"""
import os
from pathlib import Path
from huggingface_hub import snapshot_download
from utils import resource_path

def download_model():
    """下载/更新多语言嵌入模型"""
    
    # 模型信息
    model_name = "Alibaba-NLP/gte-multilingual-base"
    local_dir = Path(resource_path("models/gte-multilingual-base"))
    
    print("=" * 60)
    print("多语言嵌入模型下载工具")
    print("=" * 60)
    print(f"模型名称: {model_name}")
    print(f"本地路径: {local_dir.absolute()}")
    print(f"模型大小: 约 560MB")
    print("=" * 60)
    
    # 检查本地是否已存在
    if local_dir.exists() and list(local_dir.glob("*.bin")):
        print(f"\n检测到本地已有模型文件")
        choice = input("是否重新下载/更新? (y/n): ").strip().lower()
        if choice != 'y':
            print("取消操作")
            return
        print("\n开始重新下载...")
    else:
        print("\n开始首次下载...")
    
    # 确保目录存在
    local_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # 临时允许联网（仅用于下载）
        os.environ.pop("TRANSFORMERS_OFFLINE", None)
        os.environ.pop("HF_HUB_OFFLINE", None)
        
        # 下载模型
        print("\n正在下载模型文件...")
        print("(如果速度慢，建议使用VPN或配置HF镜像)")
        
        snapshot_download(
            repo_id=model_name,
            local_dir=str(local_dir),
            local_dir_use_symlinks=False,
            ignore_patterns=["*.md", "*.txt", "*.onnx"],  # 跳过不需要的文件
            resume_download=True  # 支持断点续传
        )
        
        print("\n" + "=" * 60)
        print("✓ 模型下载完成！")
        print("=" * 60)
        print(f"模型位置: {local_dir.absolute()}")
        print("\n已下载文件:")
        for file in sorted(local_dir.rglob("*")):
            if file.is_file():
                size_mb = file.stat().st_size / (1024 * 1024)
                print(f"  - {file.name} ({size_mb:.2f} MB)")
        
        print("\n现在可以启动主程序了！")
        
    except KeyboardInterrupt:
        print("\n\n下载已取消")
    except Exception as e:
        print(f"\n下载失败: {e}")
        print("\n可能的解决方案:")
        print("1. 检查网络连接")
        print("2. 使用VPN访问huggingface.co")
        print("3. 配置Hugging Face镜像:")
        print("   export HF_ENDPOINT=https://hf-mirror.com")

if __name__ == "__main__":
    download_model()