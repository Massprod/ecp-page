from app import app


if __name__ == "__main__":
    from waitress import serve
    app.logger.info('Starting Waitress server')
    serve(app, host='0.0.0.0', port=9898)
