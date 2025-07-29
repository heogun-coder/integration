class Config:
    SECRET_KEY = 'your-secret-key'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = 'your-jwt-secret-key'
    
    # JWT 쿠키 설정
    JWT_TOKEN_LOCATION = ['headers', 'cookies']
    JWT_COOKIE_SECURE = False  # 개발환경에서는 False, 프로덕션에서는 True
    JWT_COOKIE_CSRF_PROTECT = False  # 개발 편의를 위해 False