"""FileStorage adapters: local disk (single host) and S3-compatible (MinIO, AWS S3, R2...)."""

import shutil
from collections.abc import Iterator
from pathlib import Path

from app.domain.errors import NotFound

CHUNK = 1024 * 1024


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return path

    def put(self, key: str, source: Path) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    def get(self, key: str, destination: Path) -> Path:
        source = self._path(key)
        if not source.exists():
            raise NotFound("File no longer available.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return destination

    def open_stream(self, key: str) -> Iterator[bytes]:
        path = self._path(key)
        if not path.exists():
            raise NotFound("File no longer available. Files are deleted automatically after processing.")

        def stream() -> Iterator[bytes]:
            with path.open("rb") as fh:
                while chunk := fh.read(CHUNK):
                    yield chunk

        return stream()

    def size(self, key: str) -> int:
        return self._path(key).stat().st_size

    def delete_prefix(self, prefix: str) -> None:
        path = self._path(prefix)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink(missing_ok=True)


class S3Storage:
    def __init__(
        self, *, bucket: str, endpoint_url: str | None, access_key: str | None, secret_key: str | None, region: str
    ):
        import boto3

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, source: Path) -> None:
        self.client.upload_file(str(source), self.bucket, key)

    def get(self, key: str, destination: Path) -> Path:
        from botocore.exceptions import ClientError

        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.client.download_file(self.bucket, key, str(destination))
        except ClientError:
            raise NotFound("File no longer available.") from None
        return destination

    def open_stream(self, key: str) -> Iterator[bytes]:
        from botocore.exceptions import ClientError

        try:
            body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        except ClientError:
            raise NotFound("File no longer available. Files are deleted automatically after processing.") from None
        return body.iter_chunks(CHUNK)

    def size(self, key: str) -> int:
        return self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]

    def delete_prefix(self, prefix: str) -> None:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if keys:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys})
