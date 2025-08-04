# Integration - 통합 웹 애플리케이션

Instagram DM과 같은 실시간 채팅 및 종단간 암호화, 고급 캘린더 기능을 갖춘 통합 웹 애플리케이션입니다.

## 주요 기능

### 🔐 종단간 암호화 채팅
- **RSA + AES 하이브리드 암호화**: 메시지의 완전한 보안 보장
- **그룹 채팅 암호화**: 각 참가자마다 개별 키 분배
- **1:1 프라이빗 메시지**: 완전한 종단간 암호화
- **실시간 메시징**: Socket.IO 기반 실시간 통신
- **키 지문 검증**: 공개키 무결성 확인

### 📅 고급 캘린더 시스템
- **드래그앤드롭 이벤트 이동**: 직관적인 일정 관리
- **반복 이벤트 관리**: 일간/주간/월간 반복 일정
- **이벤트 공유**: 다른 사용자와 일정 공유 (보기/편집 권한)
- **알림 시스템**: 커스터마이징 가능한 이벤트 알림
- **색상 코딩**: 카테고리별 시각적 구분
- **우선순위 설정**: 이벤트 중요도 관리

### 💬 채팅 기능
- **그룹 채팅방**: 다중 사용자 채팅
- **실시간 타이핑 표시**: 상대방 입력 상태 확인
- **온라인 상태 표시**: 사용자 접속 상태 실시간 확인
- **메시지 답글**: 특정 메시지에 대한 답글
- **메시지 편집/삭제**: 전송된 메시지 수정 가능
- **읽음 표시**: 메시지 읽음 상태 확인

### 👥 사용자 관리
- **JWT 인증**: 안전한 토큰 기반 인증
- **키 쌍 관리**: 사용자별 RSA 키 쌍 자동 생성
- **프로필 관리**: 사용자 정보 및 설정

## 기술 스택

### Backend
- **Flask**: 웹 프레임워크
- **Flask-SQLAlchemy**: ORM
- **Flask-JWT-Extended**: JWT 인증
- **Flask-SocketIO**: 실시간 통신
- **Cryptography**: 암호화 라이브러리
- **SQLite**: 데이터베이스

### Frontend
- HTML5, CSS3, JavaScript
- Socket.IO Client
- Bootstrap (UI 프레임워크)

## 설치 및 실행

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 애플리케이션 실행
```bash
python run.py
```

애플리케이션은 기본적으로 `http://localhost:5000`에서 실행됩니다.

### 3. 기본 관리자 계정
- **사용자명**: admin
- **비밀번호**: admin123

## API 엔드포인트

### 인증 API
- `POST /api/auth/register` - 사용자 등록 (키 쌍 자동 생성)
- `POST /api/auth/login` - 로그인
- `POST /api/auth/logout` - 로그아웃
- `GET /api/auth/users/<username>/public-key` - 공개키 조회
- `POST /api/auth/verify-fingerprint` - 키 지문 검증
- `POST /api/auth/regenerate-keys` - 키 쌍 재생성

### 채팅 API
- `GET /api/chat/rooms` - 채팅방 목록
- `POST /api/chat/rooms` - 채팅방 생성 (암호화 키 자동 생성)
- `GET /api/chat/rooms/<id>/messages` - 메시지 조회
- `GET /api/chat/rooms/<id>/encryption-key` - 그룹 암호화 키 조회
- `POST /api/chat/send-encrypted` - 암호화된 메시지 전송
- `POST /api/chat/rooms/<id>/join` - 채팅방 참가 (키 분배)
- `POST /api/chat/rooms/<id>/leave` - 채팅방 나가기

### 프라이빗 메시지 API
- `GET /api/messages/conversations` - 대화 목록
- `GET /api/messages/<user_id>` - 특정 사용자와의 메시지
- `POST /api/messages` - 메시지 전송
- `POST /api/messages/send-encrypted` - 암호화된 메시지 전송
- `GET /api/messages/unread-count` - 읽지 않은 메시지 수

### 캘린더 API
- `GET /api/calendar/events` - 이벤트 조회 (공유 이벤트 포함)
- `POST /api/calendar/events` - 이벤트 생성 (반복 이벤트 지원)
- `PUT /api/calendar/events/<id>` - 이벤트 수정
- `DELETE /api/calendar/events/<id>` - 이벤트 삭제
- `PUT /api/calendar/events/<id>/move` - 드래그앤드롭 이동
- `POST /api/calendar/events/<id>/share` - 이벤트 공유
- `DELETE /api/calendar/events/<id>/unshare` - 공유 해제
- `DELETE /api/calendar/events/repeat-group/<id>` - 반복 이벤트 그룹 삭제
- `GET /api/calendar/events/<id>/notifications` - 이벤트 알림 조회

## 보안 기능

### 종단간 암호화
1. **키 생성**: 사용자 등록 시 2048비트 RSA 키 쌍 자동 생성
2. **하이브리드 암호화**: RSA로 AES 키를 암호화하고, AES로 메시지 암호화
3. **그룹 키 관리**: 각 그룹 채팅방마다 고유한 AES 키 생성
4. **키 분배**: 참가자 공개키로 그룹 키를 개별 암호화하여 분배
5. **키 지문**: SHA256 해시를 통한 공개키 무결성 검증

### 개인정보 보호
- 서버에는 개인키 저장하지 않음 (클라이언트에서 관리)
- 암호화된 메시지만 데이터베이스에 저장
- JWT 토큰 기반 인증으로 세션 보안 강화

## 데이터베이스 스키마

### 주요 테이블
- **User**: 사용자 정보 및 공개키 저장
- **ChatRoom**: 채팅방 정보 및 그룹 암호화 키
- **Message**: 암호화된 그룹 메시지
- **PrivateMessage**: 암호화된 개인 메시지
- **UserGroupKey**: 사용자별 그룹 키 암호화 저장
- **Event**: 캘린더 이벤트 (반복, 공유 정보 포함)
- **EventShare**: 이벤트 공유 정보

## Socket.IO 이벤트

### 채팅 이벤트
- `join` - 채팅방 입장
- `leave` - 채팅방 퇴장
- `message` - 메시지 전송 (암호화 지원)
- `typing` - 타이핑 상태 전송
- `ping` - 온라인 상태 유지

## 개발 가이드

### 새로운 암호화 기능 추가
1. `app/crypto.py`에 암호화 함수 구현
2. 모델에 필요한 암호화 필드 추가
3. API에서 암호화/복호화 로직 통합
4. 클라이언트에서 키 관리 구현

### 캘린더 기능 확장
1. `app/models.py`에서 Event 모델 확장
2. `app/calendar/routes.py`에 새 API 추가
3. 반복 이벤트의 경우 `create_recurring_events` 함수 수정

## 주의사항

1. **개인키 보안**: 클라이언트의 개인키는 절대 서버로 전송하지 말 것
2. **키 백업**: 사용자가 개인키를 분실하면 기존 메시지 복호화 불가
3. **성능**: 대용량 그룹 채팅 시 암호화/복호화 성능 고려 필요
4. **키 순환**: 보안을 위해 주기적인 키 재생성 권장
