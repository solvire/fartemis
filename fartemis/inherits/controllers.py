# -*- coding: utf-8 -*-
"""
Author: Steven Scott
Date: 2018-02-21

The main inherited controller files
Used to manage data models and apply business logic to them
"""
from abc import ABC
from abc import abstractmethod


class BaseController(ABC):
    """
    base controller object
    """

    name = __name__

    @abstractmethod
    def get_name(self):
        return self.name

    class Meta:
        abstract = True
