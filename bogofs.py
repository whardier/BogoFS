#!/usr/bin/env python

import sys

from errno import EACCES
from os.path import realpath
from sys import argv, exit
from threading import Lock

import os

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn

from math import floor
from hashlib import sha256
from zlib import compress, decompress

class BogoFS(LoggingMixIn, Operations):
    def __init__(self, root, backing):
        self.root = realpath(root)
        self.backing = realpath(backing)
        self.rwlock = Lock()
        self.chunksize = 2**16

    def __call__(self, op, path, *args):
        return super(BogoFS, self).__call__(op, self.root + path, *args)

    def access(self, path, mode):
        if not os.access(path, mode):
            raise FuseOSError(EACCES)

    chmod = os.chmod
    chown = os.chown

    def create(self, path, mode):
        return os.open(path, os.O_WRONLY | os.O_CREAT, mode)

    def flush(self, path, fh):
        return os.fsync(fh)

    def fsync(self, path, datasync, fh):
        return os.fsync(fh)

    def getattr(self, path, fh=None):
        st = os.lstat(path)
        return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
            'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))

    getxattr = None

    def link(self, target, source):
        return os.link(source, target)

    listxattr = None
    mkdir = os.mkdir
    mknod = os.mknod
    open = os.open

    def read(self, path, size, offset, fh):
        with self.rwlock:
            pathhash = os.path.join(self.backing, sha256(path).hexdigest())

            chunk = int(self.chunksize * floor(float(offset) / self.chunksize))
            chunkfile = os.path.join(pathhash, str(chunk))
            chunkoffset = offset - chunk

            try:
                os.makedirs(pathhash)
            except:
                pass

            try:
                data = decompress(open(chunkfile).read())
            except:
                os.lseek(fh, chunk, 0)
                data = os.read(fh, self.chunksize)

                with open(chunkfile, 'w') as f:
                    f.write(compress(data))

            return data[chunkoffset:chunkoffset+size]

    def readdir(self, path, fh):
        return ['.', '..'] + os.listdir(path)

    readlink = os.readlink

    def release(self, path, fh):
        return os.close(fh)

    def rename(self, old, new):
        return os.rename(old, self.root + new)

    rmdir = os.rmdir

    def statfs(self, path):
        stv = os.statvfs(path)
        return dict((key, getattr(stv, key)) for key in ('f_bavail', 'f_bfree',
            'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files', 'f_flag',
            'f_frsize', 'f_namemax'))

    def symlink(self, target, source):
        return os.symlink(source, target)

    def truncate(self, path, length, fh=None):
        with open(path, 'r+') as f:
            f.truncate(length)

    unlink = os.unlink
    utimens = os.utime

    def write(self, path, data, offset, fh):
        with self.rwlock:
            pathhash = os.path.join(self.backing, sha256(path).hexdigest())

            chunk = int(self.chunksize * floor(float(offset) / self.chunksize))
            chunkfile = os.path.join(pathhash, str(chunk))
            chunkoffset = offset - chunk
            size = len(data)

            try:
                os.makedirs(pathhash)
            except:
                pass

            try:
                buffer = decompress(open(chunkfile).read())
                buffer = buffer[:chunkoffset] + data + buffer[chunkoffset+size+1:]
            except:
                buffer = data

            with open(chunkfile, 'w') as f:
                f.write(compress(buffer))

            os.lseek(fh, offset, 0)
            return os.write(fh, data)

if __name__ == "__main__":
    if len(argv) != 4:
        print 'usage: %s <root> <backing> <mountpoint>' % argv[0]
        exit(1)
    fuse = FUSE(BogoFS(argv[1], argv[2]), argv[3], foreground=True)
