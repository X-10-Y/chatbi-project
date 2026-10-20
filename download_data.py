"""
下载 Olist 巴西电商数据集
运行：python download_data.py
"""
import kagglehub
import os
import shutil
# ==================== 配置 ====================
DATASET_HANDLE = "olistbr/brazilian-ecommerce"
TARGET_DIR = os.path.join(os.getcwd(), "data", "raw")
def main():
    print(f"📥 正在下载数据集: {DATASET_HANDLE}")
    print("   首次下载约 40MB，请耐心等待...")
    print("=" * 50)
    # kagglehub 会下载到缓存目录，返回路径
    cache_path = kagglehub.dataset_download(DATASET_HANDLE)
    print(f"✅ 下载完成，缓存路径: {cache_path}")
    # 复制到项目目录
    os.makedirs(TARGET_DIR, exist_ok=True)
    # 缓存目录里可能有一层子目录，遍历复制所有 CSV
    copied = 0
    for root, dirs, files in os.walk(cache_path):
        for f in files:
            if f.endswith(".csv"):
                src = os.path.join(root, f)
                dst = os.path.join(TARGET_DIR, f)
                shutil.copy2(src, dst)
                copied += 1
                size_mb = os.path.getsize(dst) / 1024 / 1024
                print(f"   ✅ {f} ({size_mb:.1f} MB)")
    print("=" * 50)
    print(f"📂 共复制 {copied} 个 CSV 文件到: {TARGET_DIR}")
    # 验证
    print("\n📊 文件清单：")
    for f in sorted(os.listdir(TARGET_DIR)):
        if f.endswith(".csv"):
            size = os.path.getsize(os.path.join(TARGET_DIR, f)) / 1024 / 1024
            print(f"   - {f}  ({size:.1f} MB)")
if __name__ == "__main__":
    main()