import json
from flask import request, Response
import werkzeug


class RESTResource(object):
    """Represents a REST resource, with the different HTTP verbs"""
    _NEED_ID = ["put", "delete"]
    _VERBS = {"get": "GET",
              "list": "GET",
              "put": "PUT",
              "update": "PUT",
              "delete": "DELETE",
              "add": "POST",
              "post": "POST",
              "head": "HEAD",
              "options": "OPTIONS",
              }

    def __init__(self, name, route, app, handler, authentifier=None,
            actions=None, inject_name=None, identifer=None):
        """
        :name:
            name of the resource. This is being used when registering
            the route, for its name and for the name of the id parameter
            that will be passed to the views

        :route:
           Default route for this resource.  If none are given, will
           iterate over all of the methods within the handler and
           add a url rule for each method.

        :app:
            Application to register the routes onto

        :actions:
            Authorized actions. Optional. None means all the actions defined in the class.

        :handler:
            The handler instance which will handle the requests

        :authentifier:
            callable checking the authentication. If specified, all the
            methods will be checked against it.

        :identifier:
            Name of key/id used to identifier specific items in all requests
            that require specific item
        """
        if not actions:
            actions = self._VERBS.keys()

        self._route = route
        self._handler = handler
        self._name = name
        self._identifier = "%s_id" % name
        if (identifer != None):
            self._identifier = identifer
        self._authentifier = authentifier
        self._inject_name = inject_name  # FIXME

        for action in actions:
            self.add_url_rule(app, action)

    def _get_route_for(self, action):
        """Return the complete URL for this action.

        Basically:

         - get, update and delete need an id
         - add and list does not
        """
        route = self._route

        if action in self._NEED_ID:
            route += "/<%s>" % self._identifier

        return route

    def add_url_rule(self, app, action):
        """Registers a new url to the given application, regarding
        the action.
        """
        method = getattr(self._handler, action, None)
        if (method != None):
            # decorate the view
            if self._authentifier:
                method = need_auth(self._authentifier,
                        self._identifier)(method)

            method = serialize(method)

            app.add_url_rule(
                self._get_route_for(action),
                "%s_%s" % (self._name, action),
                method,
                methods=[self._VERBS.get(action, "GET")])


# decorators
def need_auth(authentifier, name=None, remove_attr=True):
    """Decorator checking that the authentifier does not returns false in
    the current context.

    If the request is authorized, the object returned by the authentifier
    is added to the kwargs of the method.

    If not, issue a 401 Unauthorized error

    :authentifier:
        The callable to check the context onto.

    :name:
        **Optional**, name of the argument to put the object into.
        If it is not provided, nothing will be added to the kwargs
        of the decorated function

    :remove_attr:
        Remove or not the `*name*_id` from the kwargs before calling the
        function
    """
    def wrapper(func):
        def wrapped(*args, **kwargs):
            result = authentifier(*args, **kwargs)
            if result:
                if name:
                    kwargs[name] = result
                if remove_attr and name in kwargs:
                    del kwargs["%s" % name]
                return func(*args, **kwargs)
            else:
                return werkzeug.Response("Could not verify your access level for that URL.\n"
                        "You have to login with proper credentials", 401,
                        {'WWW-Authenticate': 'Basic realm="Login Required"'})
        return wrapped
    return wrapper


# serializers
def serialize(func):
    """If the object returned by the view is not already a Response, serialize
    it using the ACCEPT header and return it.
    """
    def wrapped(*args, **kwargs):
        # get the mimetype
        mime = request.accept_mimetypes.best_match(SERIALIZERS.keys()) or "application/json"
        data = func(*args, **kwargs)
        serializer = SERIALIZERS[mime]

        status = 200
        if (type(data) == werkzeug.Response or
            type(data) == Response):
            return data
        elif (type(tuple)):
            status, data = data

        # serialize it
        return werkzeug.Response(serializer.encode(data),
                status=status, mimetype=mime)

    return wrapped


class JSONEncoder(json.JSONEncoder):
    """Subclass of the default encoder to support custom objects"""
    def default(self, o):
        if hasattr(o, "_to_serialize"):
            # build up the object
            data = {}
            for attr in o._to_serialize:
                data[attr] = getattr(o, attr)
            return data
        elif hasattr(o, "isoformat"):
            return o.isoformat()
        else:
            return json.JSONEncoder.default(self, o)

SERIALIZERS = {"application/json": JSONEncoder(), "text/json": JSONEncoder()}
