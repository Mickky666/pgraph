import inspect
import json
import os
from functools import wraps


class _PipeMeta(type):
    _RUN_METHOD_NAME = "run"
    _FLOWPOOL_ARG_NAME = "flow_pool"
    _CONFIG_ARG_NAME = "config"
    _MODE_ARG_NAME = "mode"

    @staticmethod
    def _check_run_argspec(run_func):
        run_argspec = inspect.getargspec(run_func)
        assert len(run_argspec[0]) == 4 and \
            run_argspec[0][0] == 'self' and \
            run_argspec[0][1] == _PipeMeta._FLOWPOOL_ARG_NAME and \
            run_argspec[0][2] == _PipeMeta._CONFIG_ARG_NAME and \
            run_argspec[0][3] == _PipeMeta._MODE_ARG_NAME
        assert run_argspec[1] is None
        assert run_argspec[2] is None
        assert run_argspec[3] is None

    def __new__(typ, name, bases, func_dict):
        run_func = func_dict[_PipeMeta._RUN_METHOD_NAME]
        typ._check_run_argspec(run_func)

        def wrap_run(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                self = args[0]
                assert len(args) == 1, "Run method should be called using keyword args only."
                flow_pool = kwargs[_PipeMeta._FLOWPOOL_ARG_NAME]
                config = kwargs[_PipeMeta._CONFIG_ARG_NAME]
                flow_pool.pop_cache()
                config.pop_cache()
                func(*args, **kwargs)
                flow_cache = flow_pool.pop_cache()
                config_cache = config.pop_cache()
                self.input_flow = flow_cache[flow_pool.READ_CACHE_KEY]
                self.output_flow = flow_cache[flow_pool.WRITE_CACHE_KEY]
                self.config_used = config_cache[config.CACHE_KEY]
            return wrapper

        func_dict[_PipeMeta._RUN_METHOD_NAME] = wrap_run(run_func)
        return super(_PipeMeta, typ).__new__(typ, name, bases, func_dict)


class Pipe(object):
    __metaclass__ = _PipeMeta

    def __init__(self):
        self.input_flow = []
        self.output_flow = []
        self.config_used = dict()

    def run(self, flow_pool, config, mode):
        raise NotImplementedError

    def __rshift__(self, other):
        assert isinstance(other, Pipe), "The right side of >> operator needs to be a Pipe object."
        return Pipeline(self, other)


class Pipeline(object):

    def __init__(self, *args, **kwargs):
        assert all(isinstance(x, Pipe) for x in args), "Pipeline can only build on Pipe object."
        self.pipes = list(args)

    def run(self, use_config, running_flow_pool=None):
        running_flow_pool = FlowPool() if running_flow_pool is None else running_flow_pool
        for pipe in self.pipes:
            pipe.run(flow_pool=running_flow_pool, config=use_config, mode="run")
        return running_flow_pool

    def __rshift__(self, other):
        assert isinstance(other, Pipe), "The right side of >> operator needs to be a Pipe object."
        self.pipes.append(other)
        return self


class FlowPool(object):
    READ_CACHE_KEY = "read_cache"
    WRITE_CACHE_KEY = "write_cache"

    def __init__(self):
        self.flow_map = dict()
        self._read_cache = []
        self._write_cache = []

    def pop_cache(self):
        output = {
            self.READ_CACHE_KEY: self._read_cache,
            self.WRITE_CACHE_KEY: self._write_cache,
        }
        self._read_cache = []
        self._write_cache = []
        return output

    def read_flow(self, flow_name):
        if flow_name not in self.flow_map:
            raise Exception("Error when trying to read flow: ({}). "
                            "No such flow exists.".format(flow_name))
        if flow_name in self._read_cache:
            raise Exception("Error when trying to read flow: ({}). "
                            "Flow can only be read once in one pipe.".format(flow_name))
        if flow_name in self._write_cache:
            raise Exception("Error when trying to read flow: ({}). "
                            "Reading the same flow after writing it is not allowed".format(flow_name))
        self._read_cache.append(flow_name)
        return self.flow_map[flow_name]

    def write_flow(self, flow_name, flow_content, overwrite=False):
        if flow_name in self.flow_map and not overwrite:
            raise Exception("Error when trying to write flow: ({}). "
                            "Flow already exists when overwrite=False.".format(flow_name))
        if flow_name in self._write_cache:
            raise Exception("Error when trying to write flow: ({}). "
                            "Flow can only be written once in one pipe".format(flow_name))
        self._write_cache.append(flow_name)
        self.flow_map[flow_name] = flow_content


class Config(object):
    CACHE_KEY = "read_cache"
    SERIALIZATION_FNAME = "config.json"

    def __init__(self, start_from=None):
        self.config_map = dict() if start_from is None else start_from
        self._check_type()
        self._cache = dict()

    def _check_type(self):
        assert isinstance(self.config_map, dict)
        for config_name in self.config_map:
            assert type(self.config_map[config_name]) in (int, float, str)

    def pop_cache(self):
        output = {self.CACHE_KEY: self._cache}
        self._cache = dict()
        return output

    def get_config(self, config_name):
        if config_name not in self.config_map:
            raise Exception("Error when trying to get config: ({}). "
                            "No such config exists.".format(config_name))
        self._cache[config_name] = self.config_map[config_name]
        return self.config_map[config_name]

    def serialize_to(self, target_dir):
        # TODO(Kevin) Add support for remote serialization.
        json.dump(self.config_map, open(os.path.join(target_dir, Config.SERIALIZATION_FNAME), 'wb'))

    def serialize_from(self, source_dir):
        # TODO(Kevin) Add support for remote serialization.
        self.config_map = json.load(os.path.join(source_dir, Config.SERIALIZATION_FNAME), 'rb')



