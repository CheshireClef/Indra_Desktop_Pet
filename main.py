print("=== Indra 桌面宠物启动 ===")

# 测试配置读取
try:
    import yaml
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    print(f"宠物名字: {config['pet']['name']}")
except Exception as e:
    print(f"读取配置失败: {e}")

input("按Enter键退出...")