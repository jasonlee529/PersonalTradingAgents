def test_fastapi_importable():
    import fastapi
    assert fastapi.__version__

def test_uvicorn_importable():
    import uvicorn
    assert uvicorn.__version__
