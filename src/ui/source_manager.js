Ext.namespace("SYNO.SDS.SourceManager");
Ext.define("SYNO.SDS._ThirdParty.App.SourceManager", {
    extend: "SYNO.SDS.AppInstance",
    appWindowName: "SYNO.SDS.SourceManager.MainWindow",
    constructor: function() {
        this.callParent(arguments);
    }
});
Ext.define("SYNO.SDS.SourceManager.MainWindow", {
    extend: "SYNO.SDS.AppWindow",
    constructor: function(a) {
        this.appInstance = a.appInstance;
        SYNO.SDS.SourceManager.MainWindow.superclass.constructor.call(this, Ext.apply({
            layout: "fit",
            resizable: true,
            cls: "syno-app-win",
            maximizable: true,
            minimizable: true,
            showHelp: false,
            width: 800,
            height: 600,
            html: '<iframe src="webman/3rdparty/SourceManager/index.html?_ts=' + new Date().getTime() + '" style="width:100%;height:100%;border:none;margin:0;"></iframe>'
        }, a));
    },
    onClose: function() {
        SYNO.SDS.SourceManager.MainWindow.superclass.onClose.apply(this, arguments);
        this.doClose();
        return true;
    }
});
