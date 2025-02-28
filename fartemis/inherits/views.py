import logging

logger = logging.getLogger(__name__)

# http://stackoverflow.com/a/22922156/4848185
class MultiSerializerViewSetMixin(object):

    mapping = {
        'get': 'retrieve',
        'post': 'create',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }

    def get_serializer_class(self):
        """
        Look for serializer class in self.serializer_action_classes, which
        should be a dict mapping action name (key) to serializer class (value),
        i.e.:

        class MyViewSet(MultiSerializerViewSetMixin, ViewSet):
            serializer_class = MyDefaultSerializer
            serializer_action_classes = {
               'list': MyListSerializer,
               'my_action': MyActionSerializer,
            }

            @action
            def my_action:
                ...

        If there's no entry for that action then just fallback to the regular
        get_serializer_class lookup: self.serializer_class, DefaultSerializer.

        Thanks gonz: http://stackoverflow.com/a/22922156/11440

        """
        key = None
        if hasattr(self, 'action'):
            key = self.action
        else:
            key = self.get_mapped_action()


        logger.debug('get_serializer_class - mixin ' + str(self.request.method) + ' for key: ' + str(key))
        try:
            return self.serializer_action_classes[key]
        except (KeyError, AttributeError):
            return super(MultiSerializerViewSetMixin, self).get_serializer_class()

    def get_mapped_action(self):
        """
        The generics are always mapped to these actions. They don't have actions.
        Viewsets do.
        So map the method to the action.
        """
        method = self.request.method.lower()
        if method in self.mapping:
            return self.mapping[method]
