import os
import pickle
import sys
import types
import zipfile

class Loader(types.ModuleType):
    def __init__(self, base, zf, globals, name=""):
        super().__init__(name)
        self.base = base
        self.zf = zf
        self.globals = globals.copy()
        self.fresh_module = False
        self.compiled = False
        self.unmangle = ['_ResNet', '_Sequential', '_BasicBlock', '_Conv2d']

    def __getattr__(self, name):
        for prefix in self.unmangle:
            if name.find(prefix) == 0:
                name = name[len(prefix):]
        dirname = os.path.join(self.base, name)
        filename = dirname + '.py'
        print("{} -> {}".format(self.base, name))

        if name in self.globals:
            # Stuff in the module by this name takes precedence, then subdirs
            print("   Return existing globals for {}".format(name))
            return self.globals[name]

        if filename in self.zf.namelist() and not self.compiled:
            # If the filename names a module, compile it
            #   - the same name can also be a directory leading to other modules
            ldr = Loader(dirname, self.zf, self.globals)
            ldr.fresh_module = True
            setattr(self, name, ldr)  # Temporary class to allow annotations to work
            self.globals[name] = ldr
            f = self.zf.read(filename)
            print("   Compile: ", name)
            exec(compile(f, name, 'exec'), ldr.globals)
            ldr.fresh_module = False
            ldr.compiled = True
            print("   Return finished loader for module {}".format(name))
            return ldr

        if any([dirname in x for x in self.zf.namelist()]):
            attr = Loader(dirname, self.zf, self.globals)
            setattr(self, name, attr)
            print("   Return loader for dir {}".format(name))
            return attr

        if self.fresh_module:
            print("   Return Dummy Class for {}".format(name))
            return types.new_class("Dummy Class")

        raise AttributeError("{} not found in {}".format(name, self.base))


class TorchUnpickler(pickle.Unpickler):
    def __init__(self, resolver, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.resolver = resolver

    def find_class(self, module, name):
        print("find_class {}:{}".format(module, name))
        for step in module.split('.'):
            if step == '__torch__':
                mod = self.resolver
            else:
                mod = getattr(mod, step)
        return mod


def load(filename):

    glob = {}
    exec(compile('from torch import Tensor', 'import tensor', 'exec'), glob)
    exec(compile("class Module:  pass", 'module.py', 'exec'), glob)

    filename_no_ext = os.path.splitext(os.path.split(filename)[-1])[0]
    with zipfile.ZipFile(filename, 'r') as f:
        resolver = Loader('{}/code/__torch__'.format(filename_no_ext), f, glob, name="__torch__") 
        glob['__torch__'] = resolver
        glob['__torch__'].globals['__torch__'] = resolver
        sys.modules['__torch__'] = resolver

        for src in ['data.pkl']:  # ['constants.pkl', 'data.pkl']:
            fname = os.path.join(filename_no_ext, src)
            # pickle.load(f.open(fname)) # TypeError: 'Loader' object is not iterable assuming sys.modules[__torch__] points to resolver
            upk = TorchUnpickler(resolver, f.open(fname))
            upk.load()
            print("blah")

    return "model"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("load_file", help="File to load model from")
    args = parser.parse_args()

    model = load(args.load_file)