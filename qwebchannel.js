"use strict";

var QWebChannelMessageTypes = {
    QtSignal: 1,
    QtPropertyUpdate: 2,
    QtInit: 3,
    QtIdle: 4,
    QtDebug: 5,
    QtCall: 6,
    QtReply: 7,
    QtPropertySet: 8,
    QtSignalEmitter: 9
};

var QWebChannel = function (transport, initCallback) {
    if (typeof transport !== "object" || typeof transport.send !== "function") {
        console.error("The QWebChannel transport object is invalid!");
        return;
    }

    var channel = this;
    this.transport = transport;

    this.send = function (data) {
        if (typeof data !== "string") {
            data = JSON.stringify(data);
        }
        channel.transport.send(data);
    };

    this.transport.onmessage = function (message) {
        var data = message.data;
        if (typeof data === "string") {
            data = JSON.parse(data);
        }
        switch (data.type) {
            case QWebChannelMessageTypes.QtSignal:
                channel.handleSignal(data);
                break;
            case QWebChannelMessageTypes.QtPropertyUpdate:
                channel.handlePropertyUpdate(data);
                break;
            case QWebChannelMessageTypes.QtReply:
                channel.handleReply(data);
                break;
            case QWebChannelMessageTypes.QtDebug:
                console.log(data.message);
                break;
            case QWebChannelMessageTypes.QtIdle:
                break;
            default:
                console.error("invalid message type: " + data.type);
                break;
        }
    };

    this.objects = {};
    this.callbacks = {};
    this.callbackId = 0;

    this.handleSignal = function (message) {
        var object = channel.objects[message.object];
        if (object) {
            object.signals[message.signal].emit.apply(object.signals[message.signal], message.args);
        }
    };

    this.handlePropertyUpdate = function (message) {
        for (var i in message.signals) {
            var signal = message.signals[i];
            var object = channel.objects[signal.object];
            if (object) {
                object.signals[signal.signal].emit.apply(object.signals[signal.signal], signal.args);
            }
        }
    };

    this.handleReply = function (message) {
        var callback = channel.callbacks[message.id];
        if (callback) {
            callback(message.payload);
            delete channel.callbacks[message.id];
        }
    };

    this.debug = function (message) {
        channel.send({ type: QWebChannelMessageTypes.QtDebug, message: message });
    };

    this.exec = function (data, callback) {
        if (callback) {
            var id = ++channel.callbackId;
            channel.callbacks[id] = callback;
            data.id = id;
        }
        channel.send(data);
    };

    this.init = function (data) {
        for (var name in data.objects) {
            channel.objects[name] = new QObject(name, data.objects[name], channel);
        }
    };

    this.exec({ type: QWebChannelMessageTypes.QtInit }, function (data) {
        channel.init(data);
        if (initCallback) {
            initCallback(channel);
        }
    });
};

var QObject = function (name, data, channel) {
    this.__id__ = name;
    this.signals = {};
    this.properties = {};
    this.methods = {};

    var object = this;

    for (var i in data.signals) {
        var signalName = data.signals[i];
        this.signals[signalName] = {
            connect: function (callback) {
                if (typeof callback !== "function") return;
                if (!this.connections) this.connections = [];
                this.connections.push(callback);
            },
            emit: function () {
                if (this.connections) {
                    for (var i in this.connections) {
                        this.connections[i].apply(null, arguments);
                    }
                }
            }
        };
    }

    for (var i in data.methods) {
        var methodName = data.methods[i];
        this[methodName] = (function (methodName) {
            return function () {
                var args = [];
                var callback;
                for (var i = 0; i < arguments.length; ++i) {
                    if (typeof arguments[i] === "function") {
                        callback = arguments[i];
                    } else {
                        args.push(arguments[i]);
                    }
                }
                channel.exec({
                    type: QWebChannelMessageTypes.QtCall,
                    object: object.__id__,
                    method: methodName,
                    args: args
                }, callback);
            };
        })(methodName);
    }
};
