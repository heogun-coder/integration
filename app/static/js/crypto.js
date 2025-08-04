/**
 * 클라이언트 사이드 종단간 암호화 라이브러리
 * RSA (키 교환) + AES (메시지 암호화) 하이브리드 암호화
 */

class ClientCrypto {
    constructor() {
        this.currentUserKeys = null;
        this.groupKeys = new Map(); // roomId -> AES key
        this.userPublicKeys = new Map(); // username -> public key
    }

    /**
     * 사용자의 RSA 키 쌍을 로드합니다
     */
    async loadUserKeys() {
        console.log('[Crypto] 키 로딩 시작...');
        try {
            const response = await fetch('/api/auth/my-keys', {
                headers: { 'Authorization': 'Bearer ' + localStorage.getItem('token') }
            });
            
            console.log('[Crypto] /my-keys 응답 상태:', response.status);
            if (!response.ok) {
                console.error('[Crypto] API에서 키를 가져오지 못했습니다.');
                return false;
            }

            const keys = await response.json();
            console.log('[Crypto] API에서 받은 키:', keys);
            
            if (!keys.public_key) {
                console.error('[Crypto] 응답에 공개키가 없습니다.');
                return false;
            }
            
            let publicKey, privateKey;

            try {
                publicKey = await this.importRSAKey(keys.public_key, 'public');
                console.log('[Crypto] 공개키 임포트 성공');
            } catch (e) {
                console.error('[Crypto] 공개키 임포트 실패:', e);
                return false;
            }

            // 1. 서버에서 받은 개인키로 시도
            if (keys.private_key) {
                try {
                    privateKey = await this.importRSAKey(keys.private_key, 'private');
                    console.log('[Crypto] DB의 개인키 임포트 성공');
                } catch (e) {
                    console.warn('[Crypto] DB의 개인키 임포트 실패, 로컬스토리지에서 시도합니다.', e);
                    privateKey = null; // 실패 시 null로 초기화
                }
            }

            // 2. 로컬스토리지에서 시도 (서버에 없거나 실패한 경우)
            if (!privateKey) {
                const storedPrivateKey = localStorage.getItem('user_private_key');
                console.log('[Crypto] 로컬스토리지 개인키:', storedPrivateKey ? '있음' : '없음');
                if (storedPrivateKey) {
                     try {
                        privateKey = await this.importRSAKey(storedPrivateKey, 'private');
                        console.log('[Crypto] 로컬스토리지의 개인키 임포트 성공');
                    } catch (e) {
                        console.error('[Crypto] 로컬스토리지의 개인키 임포트 실패:', e);
                    }
                }
            }
            
            if (publicKey && privateKey) {
                this.currentUserKeys = {
                    publicKey: publicKey,
                    privateKey: privateKey,
                    fingerprint: keys.key_fingerprint
                };
                console.log('[Crypto] 키 로딩 및 설정 최종 성공!');
                return true;
            } else {
                console.error('[Crypto] 개인키를 최종적으로 로드할 수 없습니다. 암호화가 비활성화됩니다.');
                return false;
            }
        } catch (error) {
            console.error('[Crypto] 키 로드 중 예외 발생:', error);
            return false;
        }
    }

    /**
     * 다른 사용자의 공개키를 가져옵니다
     */
    async getUserPublicKey(username) {
        if (this.userPublicKeys.has(username)) {
            return this.userPublicKeys.get(username);
        }

        try {
            const response = await fetch(`/api/auth/user-public-key/${username}`, {
                headers: {
                    'Authorization': 'Bearer ' + localStorage.getItem('token')
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                const publicKey = await this.importRSAKey(data.public_key, 'public');
                this.userPublicKeys.set(username, publicKey);
                return publicKey;
            }
        } catch (error) {
            console.error('공개키 가져오기 실패:', error);
        }
        return null;
    }

    /**
     * 채팅방의 AES 그룹 키를 로드합니다
     */
    async loadGroupKey(roomId) {
        if (this.groupKeys.has(roomId)) {
            return this.groupKeys.get(roomId);
        }

        try {
            const response = await fetch(`/api/chat/rooms/${roomId}/encryption-key`, {
                headers: {
                    'Authorization': 'Bearer ' + localStorage.getItem('token')
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.encrypted_group_key && this.currentUserKeys?.privateKey) {
                    // RSA로 암호화된 그룹 키를 복호화
                    const decryptedKey = await this.rsaDecrypt(
                        this.base64ToArrayBuffer(data.encrypted_group_key),
                        this.currentUserKeys.privateKey
                    );
                    
                    // AES 키로 임포트
                    const aesKey = await window.crypto.subtle.importKey(
                        'raw',
                        decryptedKey,
                        { name: 'AES-GCM' },
                        false,
                        ['encrypt', 'decrypt']
                    );
                    
                    this.groupKeys.set(roomId, aesKey);
                    return aesKey;
                }
            }
        } catch (error) {
            console.error('그룹 키 로드 실패:', error);
        }
        return null;
    }

    /**
     * 1:1 채팅용 메시지 암호화 (RSA 직접 사용)
     */
    async encryptForUser(message, username) {
        const publicKey = await this.getUserPublicKey(username);
        if (!publicKey) {
            throw new Error('사용자 공개키를 찾을 수 없습니다');
        }

        const messageBuffer = new TextEncoder().encode(message);
        const encryptedBuffer = await this.rsaEncrypt(messageBuffer, publicKey);
        return this.arrayBufferToBase64(encryptedBuffer);
    }

    /**
     * 1:1 채팅용 메시지 복호화
     */
    async decryptFromUser(encryptedMessage) {
        if (!this.currentUserKeys?.privateKey) {
            throw new Error('개인키가 없습니다');
        }

        const encryptedBuffer = this.base64ToArrayBuffer(encryptedMessage);
        const decryptedBuffer = await this.rsaDecrypt(encryptedBuffer, this.currentUserKeys.privateKey);
        return new TextDecoder().decode(decryptedBuffer);
    }

    /**
     * 그룹 채팅용 메시지 암호화 (AES 사용)
     */
    async encryptForGroup(message, roomId) {
        const groupKey = await this.loadGroupKey(roomId);
        if (!groupKey) {
            throw new Error('그룹 키를 찾을 수 없습니다');
        }

        const messageBuffer = new TextEncoder().encode(message);
        const iv = window.crypto.getRandomValues(new Uint8Array(12)); // GCM needs 12 bytes IV
        
        const encryptedBuffer = await window.crypto.subtle.encrypt(
            {
                name: 'AES-GCM',
                iv: iv
            },
            groupKey,
            messageBuffer
        );

        // IV + encrypted data를 합쳐서 반환
        const combined = new Uint8Array(iv.length + encryptedBuffer.byteLength);
        combined.set(iv);
        combined.set(new Uint8Array(encryptedBuffer), iv.length);
        
        return this.arrayBufferToBase64(combined.buffer);
    }

    /**
     * 그룹 채팅용 메시지 복호화
     */
    async decryptFromGroup(encryptedMessage, roomId) {
        const groupKey = await this.loadGroupKey(roomId);
        if (!groupKey) {
            throw new Error('그룹 키를 찾을 수 없습니다');
        }

        const combined = this.base64ToArrayBuffer(encryptedMessage);
        const iv = combined.slice(0, 12);
        const encrypted = combined.slice(12);

        const decryptedBuffer = await window.crypto.subtle.decrypt(
            {
                name: 'AES-GCM',
                iv: iv
            },
            groupKey,
            encrypted
        );

        return new TextDecoder().decode(decryptedBuffer);
    }

    /**
     * RSA 키 임포트
     */
    async importRSAKey(pemKey, type) {
        try {
            // PEM 헤더/푸터 제거 및 base64 디코딩
            const pemHeader = type === 'public' ? '-----BEGIN PUBLIC KEY-----' : '-----BEGIN PRIVATE KEY-----';
            const pemFooter = type === 'public' ? '-----END PUBLIC KEY-----' : '-----END PRIVATE KEY-----';
            
            const pemContents = pemKey
                .replace(pemHeader, '')
                .replace(pemFooter, '')
                .replace(/\s/g, '');
                
            const keyBuffer = this.base64ToArrayBuffer(pemContents);
            
            const keyFormat = type === 'public' ? 'spki' : 'pkcs8';
            const keyUsages = type === 'public' ? ['encrypt'] : ['decrypt'];
            
            return await window.crypto.subtle.importKey(
                keyFormat,
                keyBuffer,
                {
                    name: 'RSA-OAEP',
                    hash: 'SHA-256'
                },
                false,
                keyUsages
            );
        } catch (error) {
            console.error(`RSA ${type} 키 임포트 실패:`, error);
            throw error;
        }
    }

    /**
     * RSA 암호화
     */
    async rsaEncrypt(data, publicKey) {
        return await window.crypto.subtle.encrypt(
            {
                name: 'RSA-OAEP'
            },
            publicKey,
            data
        );
    }

    /**
     * RSA 복호화
     */
    async rsaDecrypt(encryptedData, privateKey) {
        return await window.crypto.subtle.decrypt(
            {
                name: 'RSA-OAEP'
            },
            privateKey,
            encryptedData
        );
    }

    /**
     * Base64 to ArrayBuffer
     */
    base64ToArrayBuffer(base64) {
        const binaryString = window.atob(base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        return bytes.buffer;
    }

    /**
     * ArrayBuffer to Base64
     */
    arrayBufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return window.btoa(binary);
    }

    /**
     * 메시지가 암호화되었는지 확인
     */
    isEncrypted(message) {
        // Base64 패턴 확인 (간단한 휴리스틱)
        return /^[A-Za-z0-9+/=]+$/.test(message) && message.length > 100;
    }

    /**
     * 암호화 지원 여부 확인
     */
    isSupported() {
        return !!(window.crypto && window.crypto.subtle);
    }
}

// 전역 인스턴스 생성
window.clientCrypto = new ClientCrypto();

// 초기화 함수
window.initializeCrypto = async function() {
    if (!window.clientCrypto.isSupported()) {
        console.warn('Web Crypto API가 지원되지 않습니다. 암호화가 비활성화됩니다.');
        return false;
    }

    try {
        const success = await window.clientCrypto.loadUserKeys();
        if (success) {
            console.log('암호화 시스템이 초기화되었습니다.');
            return true;
        } else {
            console.warn('사용자 키를 로드할 수 없습니다.');
            return false;
        }
    } catch (error) {
        console.error('암호화 초기화 실패:', error);
        return false;
    }
};