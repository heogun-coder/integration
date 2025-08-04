"""
종단간 암호화를 위한 암호화 모듈
RSA와 AES를 결합한 하이브리드 암호화 방식 사용
"""

import os
import base64
import json
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asym_padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding


class MessageCrypto:
    """메시지 암호화/복호화를 담당하는 클래스"""
    
    @staticmethod
    def generate_key_pair():
        """RSA 키 쌍 생성"""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        public_key = private_key.public_key()
        
        # 키를 PEM 형식으로 직렬화
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        
        return private_pem, public_pem
    
    @staticmethod
    def encrypt_message(message, recipient_public_key_pem):
        """메시지를 하이브리드 암호화로 암호화"""
        # 1. AES 키 생성 (256비트)
        aes_key = os.urandom(32)
        iv = os.urandom(16)
        
        # 2. AES로 메시지 암호화
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        
        # 패딩 추가
        padder = sym_padding.PKCS7(128).padder()
        padded_data = padder.update(message.encode('utf-8'))
        padded_data += padder.finalize()
        
        encrypted_message = encryptor.update(padded_data) + encryptor.finalize()
        
        # 3. RSA로 AES 키 암호화
        public_key = serialization.load_pem_public_key(
            recipient_public_key_pem.encode('utf-8'),
            backend=default_backend()
        )
        
        encrypted_aes_key = public_key.encrypt(
            aes_key,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        # 4. 결과를 JSON으로 패키징하고 base64 인코딩
        encrypted_data = {
            'encrypted_message': base64.b64encode(encrypted_message).decode('utf-8'),
            'encrypted_key': base64.b64encode(encrypted_aes_key).decode('utf-8'),
            'iv': base64.b64encode(iv).decode('utf-8')
        }
        
        return base64.b64encode(json.dumps(encrypted_data).encode('utf-8')).decode('utf-8')
    
    @staticmethod
    def decrypt_message(encrypted_data, private_key_pem):
        """암호화된 메시지를 복호화"""
        try:
            # 1. base64 디코딩 및 JSON 파싱
            decoded_data = json.loads(base64.b64decode(encrypted_data.encode('utf-8')).decode('utf-8'))
            
            encrypted_message = base64.b64decode(decoded_data['encrypted_message'].encode('utf-8'))
            encrypted_aes_key = base64.b64decode(decoded_data['encrypted_key'].encode('utf-8'))
            iv = base64.b64decode(decoded_data['iv'].encode('utf-8'))
            
            # 2. RSA로 AES 키 복호화
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode('utf-8'),
                password=None,
                backend=default_backend()
            )
            
            aes_key = private_key.decrypt(
                encrypted_aes_key,
                asym_padding.OAEP(
                    mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            # 3. AES로 메시지 복호화
            cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            
            decrypted_padded = decryptor.update(encrypted_message) + decryptor.finalize()
            
            # 패딩 제거
            unpadder = sym_padding.PKCS7(128).unpadder()
            decrypted_message = unpadder.update(decrypted_padded)
            decrypted_message += unpadder.finalize()
            
            return decrypted_message.decode('utf-8')
            
        except Exception as e:
            raise ValueError(f"복호화 실패: {str(e)}")
    
    @staticmethod
    def generate_fingerprint(public_key_pem):
        """공개키의 지문 생성"""
        public_key = serialization.load_pem_public_key(
            public_key_pem.encode('utf-8'),
            backend=default_backend()
        )
        
        # 공개키를 DER 형식으로 직렬화한 후 SHA256 해시
        der_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(der_bytes)
        fingerprint = digest.finalize()
        
        # 16진수 문자열로 변환 (콜론으로 구분)
        hex_fingerprint = fingerprint.hex().upper()
        return ':'.join([hex_fingerprint[i:i+2] for i in range(0, len(hex_fingerprint), 2)])[:47]  # 처음 24바이트만 사용


class GroupCrypto:
    """그룹 채팅 암호화를 담당하는 클래스 (AES-GCM 사용)"""
    
    @staticmethod
    def generate_group_key():
        """그룹 채팅용 256비트(32바이트) 공유 키 생성"""
        return os.urandom(32) # Base64 인코딩 없이 순수 바이트 반환
    
    @staticmethod
    def encrypt_group_key_for_user(group_key_bytes, user_public_key_pem):
        """사용자의 공개키로 그룹 키를 암호화 (RSA-OAEP)"""
        public_key = serialization.load_pem_public_key(
            user_public_key_pem.encode('utf-8'),
            backend=default_backend()
        )
        
        encrypted_group_key = public_key.encrypt(
            group_key_bytes, # 순수 바이트를 직접 암호화
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        return base64.b64encode(encrypted_group_key).decode('utf-8')
    
    @staticmethod
    def decrypt_group_key_for_user(encrypted_group_key_b64, user_private_key_pem):
        """사용자의 개인키로 그룹 키를 복호화 (RSA-OAEP)"""
        private_key = serialization.load_pem_private_key(
            user_private_key_pem.encode('utf-8'),
            password=None,
            backend=default_backend()
        )
        
        encrypted_key_bytes = base64.b64decode(encrypted_group_key_b64.encode('utf-8'))
        
        decrypted_group_key_bytes = private_key.decrypt(
            encrypted_key_bytes,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        return decrypted_group_key_bytes # 순수 바이트 반환