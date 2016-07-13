#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable= no-self-use
"""Policy for selecting appropriate function to call."""
from .. import array
from ..utils import log
from ..array_variants import ArrayType

# pylint: disable= invalid-name
_logger = log.get_logger(__name__)
# pylint: enable= invalid-name


class PrimitivePolicyError(ValueError):
    """Error during choosing primitives."""
    pass


class Policy(object):
    """Policy interface."""

    def decide(self, candidates, args, kwargs):
        """Primitive decision policy interface.

        :param list candidates: A list of primitive objects.
        :param list args: The positional arguments passed to the primitive.
        :param dict kwargs: The keyword arguments passed to the primitive.
        :return: Which implementation type will be used.
        """
        raise PrimitivePolicyError('Unimplemented.')

    @property
    def name(self):
        return type(self).__name__


class PreferMXNetPolicy(Policy):
    """Perfer using MXNet functions."""

    def decide(self, candidates, args, kwargs):
        possible_impl = set(x.type for x in candidates)
        if ArrayType.MXNET in possible_impl:
            return ArrayType.MXNET
        elif ArrayType.NUMPY in possible_impl:
            return ArrayType.NUMPY
        else:
            return None


class OnlyNumpyPolicy(Policy):
    """Perfer using MXNet functions."""

    def decide(self, candidates, args, kwargs):
        if ArrayType.NUMPY in [x.type for x in candidates]:
            return ArrayType.NUMPY
        else:
            return None


def resolve_name(name, reg, plc, args, kwargs):
    """Resolve a function name.

    :param str name: Name of the function.
    :param reg: Registry for functions.
    :param Policy plc: Resolving policy.
    :param tuple args: Positional arguments.
    :param dict kwargs: Keyword arguments.
    :return: A function after resolution.
    """
    def fst(t):
        x, _ = t
        return x
    bp_args = tuple(map(fst, filter(lambda x: isinstance(
        x[1], array.Value) and x[1].marked_for_bp, enumerate(args))))
    bp_kwargs = tuple(map(fst, filter(lambda x: isinstance(
        x[1], array.Value) and x[1].marked_for_bp, kwargs.items())))
    if not reg.has_name:
        raise ValueError(
            "Cannot find function: {}() in the primitive registry.".format(name))
    available = reg.iter_available_types(name, bp_args, bp_kwargs)
    preference = plc.decide(available, args, kwargs)
    if preference is None:
        raise ValueError(
            "Cannot find gradient implementation for function: {}() under "
            "policy: {}.".format(name, plc.name))
    return reg.get(name, preference)
