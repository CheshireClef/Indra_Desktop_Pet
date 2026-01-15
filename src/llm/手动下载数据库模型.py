from huggingface_hub import snapshot_download

# 下载模型到本地文件夹（比如 ./multilingual-e5-small）
model_local_dir = snapshot_download(
    repo_id="intfloat/multilingual-e5-small",
    local_dir="./multilingual-e5-small",
    local_dir_use_symlinks=False  # 禁用符号链接，避免打包异常
)
print(f"模型已完整下载到：{model_local_dir}")