"""S3-compatible object storage: MinIO locally, Cloudflare R2 in production.

One code path, two environments — the only difference is `S3_ENDPOINT_URL` and the
credentials in the env. Nothing here knows which one it is talking to.

The bucket is private. `put` never sets a public ACL and there is no method that returns
a permanent URL, because a permanent URL to a member's photo is a permanent leak.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.domain.errors import EvidenceNotFound

# No evidence URL ever lives longer than this, whatever config says.
MAX_URL_TTL_SECONDS = 15 * 60


class S3ImageStorage:
    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        region: str = "auto",
        access_key: str | None = None,
        secret_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._bucket = bucket
        self._client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            # SigV4 is what R2 requires; MinIO accepts it too.
            config=Config(signature_version="s3v4"),
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            # No ACL argument at all: the object inherits the bucket's private policy.
        )

    def get(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as e:
            # A caller can send a well-formed key for an object that was never uploaded.
            # That is a 404, not a server fault.
            code = e.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404", "NotFound"):
                raise EvidenceNotFound(key) from e
            raise
        body: bytes = response["Body"].read()
        return body

    def presigned_url(self, key: str, expires_in: timedelta) -> str:
        # Clamped: a misconfigured EVIDENCE_URL_TTL_SECONDS must not be able to mint
        # links to members' photos that stay valid for days.
        seconds = min(max(int(expires_in.total_seconds()), 1), MAX_URL_TTL_SECONDS)
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=seconds,
        )
        return url
