from app import create_app


app = create_app()


if __name__ == "__main__":
    # debug=False: 关闭 Flask reloader, 单进程运行, 避免双实例并发抢 SQLite 锁
    app.run(host="127.0.0.1", port=5000, debug=False)
