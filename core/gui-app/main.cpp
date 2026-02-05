#include <QApplication>
#include <QComboBox>
#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QMainWindow>
#include <QPushButton>
#include <QSlider>
#include <QSpinBox>
#include <QStackedWidget>
#include <QTextEdit>
#include <QTextStream>
#include <QTreeWidget>
#include <QVBoxLayout>
#include <QCheckBox>
#include <QProcess>
#include <QStandardPaths>
#include <QSysInfo>

#include <functional>
#include <unordered_map>
#include <vector>

struct SliderField {
    QSlider *slider;
    QSpinBox *spin;
    QLineEdit *overrideEdit;
};

struct CommandWidgets {
    QWidget *panel;
    std::function<QString()> buildCommand;
};

struct CommandDefinition {
    QString name;
    QStringList categories;
    QString baseCommand;
    std::function<CommandWidgets()> builder;
};

class MainWindow : public QMainWindow {
public:
    MainWindow() {
        setWindowTitle("Sanbot MCU Command Console");
        auto *central = new QWidget;
        auto *layout = new QHBoxLayout(central);

        auto *leftPanel = new QWidget;
        auto *leftLayout = new QVBoxLayout(leftPanel);
        auto *searchBox = new QLineEdit;
        searchBox->setPlaceholderText("Search commands");
        commandTree = new QTreeWidget;
        commandTree->setHeaderHidden(true);
        commandTree->setRootIsDecorated(true);
        commandTree->header()->setStretchLastSection(true);
        leftLayout->addWidget(searchBox);
        leftLayout->addWidget(commandTree);

        auto *rightPanel = new QWidget;
        auto *rightLayout = new QVBoxLayout(rightPanel);
        commandStack = new QStackedWidget;
        auto *emptyPanel = new QWidget;
        commandStack->addWidget(emptyPanel);
        commandStack->setCurrentWidget(emptyPanel);

        auto *sendRow = new QHBoxLayout;
        sendButton = new QPushButton("Send command");
        sendRow->addStretch();
        sendRow->addWidget(sendButton);

        outputLog = new QTextEdit;
        outputLog->setReadOnly(true);
        outputLog->setMinimumHeight(140);

        auto *hexBox = new QGroupBox("Custom HEX command");
        auto *hexLayout = new QVBoxLayout(hexBox);
        hexInput = new QLineEdit;
        hexInput->setPlaceholderText("AA BB CC 01 02");
        hexSend = new QPushButton("Send HEX bytes");
        hexLayout->addWidget(hexInput);
        hexLayout->addWidget(hexSend);

        rightLayout->addWidget(commandStack);
        rightLayout->addLayout(sendRow);
        rightLayout->addWidget(buildExecutionPanel());
        rightLayout->addWidget(outputLog);
        rightLayout->addWidget(buildSshPanel());
        rightLayout->addWidget(hexBox);

        layout->addWidget(leftPanel, 1);
        layout->addWidget(rightPanel, 2);
        setCentralWidget(central);

        populateCommands();
        rebuildTree();

        connect(searchBox, &QLineEdit::textChanged, this, &MainWindow::applyFilter);
        connect(commandTree, &QTreeWidget::itemSelectionChanged, this, &MainWindow::selectCommand);
        connect(sendButton, &QPushButton::clicked, this, &MainWindow::sendSelectedCommand);
        connect(hexSend, &QPushButton::clicked, this, &MainWindow::sendHexCommand);
        connect(openTerminal, &QPushButton::clicked, this, &MainWindow::launchTerminal);
    }

private:
    QTreeWidget *commandTree;
    QStackedWidget *commandStack;
    QPushButton *sendButton;
    QCheckBox *verboseEnabled;
    QCheckBox *testEnabled;
    QTextEdit *outputLog;
    QLineEdit *hexInput;
    QPushButton *hexSend;
    QLineEdit *sshHost;
    QLineEdit *sshUser;
    QLineEdit *sshDirectory;
    QCheckBox *sshEnabled;
    QPushButton *openTerminal;

    std::vector<CommandDefinition> commands;
    std::unordered_map<QTreeWidgetItem *, int> commandIndex;
    CommandWidgets activeWidgets{};

    void populateCommands() {
        commands.clear();

        const QVector<QPair<QString, QString>> wheelActions = {
            {"Forward", "forward"},
            {"Back", "back"},
            {"Left", "left"},
            {"Right", "right"},
            {"Left forward", "left-forward"},
            {"Right forward", "right-forward"},
            {"Left back", "left-back"},
            {"Right back", "right-back"},
            {"Left translation", "left-translation"},
            {"Right translation", "right-translation"},
            {"Turn left", "turn-left"},
            {"Turn right", "turn-right"},
            {"Stop turn", "stop-turn"},
            {"Stop", "stop"}
        };
        const QVector<QPair<QString, QString>> armParts = {
            {"Left", "left"},
            {"Right", "right"},
            {"Both", "both"}
        };
        const QVector<QPair<QString, QString>> armActions = {
            {"Up", "up"},
            {"Down", "down"},
            {"Stop", "stop"},
            {"Reset", "reset"}
        };
        const QVector<QPair<QString, QString>> headActions = {
            {"Stop", "stop"},
            {"Up", "up"},
            {"Down", "down"},
            {"Left", "left"},
            {"Right", "right"},
            {"Left up", "left-up"},
            {"Right up", "right-up"},
            {"Left down", "left-down"},
            {"Right down", "right-down"},
            {"Vertical reset", "vertical-reset"},
            {"Horizontal reset", "horizontal-reset"},
            {"Centre reset", "centre-reset"}
        };
        const QVector<QPair<QString, QString>> headAbsActions = {
            {"Vertical", "vertical"},
            {"Horizontal", "horizontal"}
        };
        const QVector<QPair<QString, QString>> headLockActions = {
            {"No lock", "no-lock"},
            {"Horizontal lock", "horizontal-lock"},
            {"Vertical lock", "vertical-lock"},
            {"Both lock", "both-lock"}
        };
        const QVector<QPair<QString, QString>> headHorizontalDirections = {
            {"Left", "left"},
            {"Right", "right"}
        };
        const QVector<QPair<QString, QString>> headVerticalDirections = {
            {"Up", "up"},
            {"Down", "down"}
        };

        commands.push_back(CommandDefinition{
            "Wheel distance",
            {"Locomotion", "Wheels"},
            "wheel-distance",
            [this, wheelActions]() {
                auto *panel = new QWidget;
                auto *layout = new QVBoxLayout(panel);
                auto *actionBox = addComboRow(layout, "Action", wheelActions);
                SliderField speedField = createByteField("Speed", 50, layout);
                SliderField distanceField = createU16Field("Distance", 1000, layout);
                auto *overrideEdit = addOverrideRow(layout, "wheel-distance forward 50 1000");
                auto buildCommand = [this, actionBox, speedField, distanceField, overrideEdit]() {
                    auto overrideText = overrideEdit->text().trimmed();
                    if (!overrideText.isEmpty()) {
                        return overrideText;
                    }
                    auto action = comboValue(actionBox);
                    return QString("wheel-distance %1 %2 %3")
                        .arg(action, valueFromField(speedField), valueFromField(distanceField));
                };
                return CommandWidgets{panel, buildCommand};
            }
        });

        commands.push_back(CommandDefinition{
            "Wheel relative",
            {"Locomotion", "Wheels"},
            "wheel-relative",
            [this, wheelActions]() {
                auto *panel = new QWidget;
                auto *layout = new QVBoxLayout(panel);
                auto *actionBox = addComboRow(layout, "Action", wheelActions);
                SliderField speedField = createByteField("Speed", 50, layout);
                SliderField angleField = createU16Field("Angle", 90, layout);
                auto *overrideEdit = addOverrideRow(layout, "wheel-relative forward 50 90");
                auto buildCommand = [this, actionBox, speedField, angleField, overrideEdit]() {
                    auto overrideText = overrideEdit->text().trimmed();
                    if (!overrideText.isEmpty()) {
                        return overrideText;
                    }
                    auto action = comboValue(actionBox);
                    return QString("wheel-relative %1 %2 %3")
                        .arg(action, valueFromField(speedField), valueFromField(angleField));
                };
                return CommandWidgets{panel, buildCommand};
            }
        });

        commands.push_back(CommandDefinition{
            "Wheel no-angle",
            {"Locomotion", "Wheels"},
            "wheel-no-angle",
            [this, wheelActions]() {
                auto *panel = new QWidget;
                auto *layout = new QVBoxLayout(panel);
                auto *actionBox = addComboRow(layout, "Action", wheelActions);
                SliderField speedField = createByteField("Speed", 50, layout);
                SliderField durationField = createU16Field("Duration", 1000, layout);
                SliderField modeField = createByteField("Duration mode", 0, layout);
                auto *overrideEdit = addOverrideRow(layout, "wheel-no-angle forward 50 1000 0");
                auto buildCommand = [this, actionBox, speedField, durationField, modeField, overrideEdit]() {
                    auto overrideText = overrideEdit->text().trimmed();
                    if (!overrideText.isEmpty()) {
                        return overrideText;
                    }
                    auto action = comboValue(actionBox);
                    return QString("wheel-no-angle %1 %2 %3 %4")
                        .arg(action, valueFromField(speedField),
                             valueFromField(durationField), valueFromField(modeField));
                };
                return CommandWidgets{panel, buildCommand};
            }
        });

        commands.push_back(CommandDefinition{
            "Wheel timed",
            {"Locomotion", "Wheels"},
            "wheel-timed",
            [this, wheelActions]() {
                auto *panel = new QWidget;
                auto *layout = new QVBoxLayout(panel);
                auto *actionBox = addComboRow(layout, "Action", wheelActions);
                SliderField timeField = createU16Field("Time", 1000, layout);
                SliderField degreeField = createByteField("Degree", 90, layout);
                auto *overrideEdit = addOverrideRow(layout, "wheel-timed forward 1000 90");
                auto buildCommand = [this, actionBox, timeField, degreeField, overrideEdit]() {
                    auto overrideText = overrideEdit->text().trimmed();
                    if (!overrideText.isEmpty()) {
                        return overrideText;
                    }
                    auto action = comboValue(actionBox);
                    return QString("wheel-timed %1 %2 %3")
                        .arg(action, valueFromField(timeField), valueFromField(degreeField));
                };
                return CommandWidgets{panel, buildCommand};
            }
        });

        commands.push_back(CommandDefinition{
            "Arm no-angle",
            {"Locomotion", "Arms"},
            "arm-no-angle",
            [this, armParts, armActions]() {
                auto *panel = new QWidget;
                auto *layout = new QVBoxLayout(panel);
                auto *partBox = addComboRow(layout, "Part", armParts);
                SliderField speedField = createByteField("Speed", 40, layout);
                auto *actionBox = addComboRow(layout, "Action", armActions);
                auto *overrideEdit = addOverrideRow(layout, "arm-no-angle left 40 up");
                auto buildCommand = [this, partBox, speedField, actionBox, overrideEdit]() {
                    auto overrideText = overrideEdit->text().trimmed();
                    if (!overrideText.isEmpty()) {
                        return overrideText;
                    }
                    return QString("arm-no-angle %1 %2 %3")
                        .arg(comboValue(partBox), valueFromField(speedField), comboValue(actionBox));
                };
                return CommandWidgets{panel, buildCommand};
            }
        });

        commands.push_back(CommandDefinition{
            "Arm relative",
            {"Locomotion", "Arms"},
            "arm-relative",
            [this, armParts, armActions]() {
                auto *panel = new QWidget;
                auto *layout = new QVBoxLayout(panel);
                auto *partBox = addComboRow(layout, "Part", armParts);
                SliderField speedField = createByteField("Speed", 40, layout);
                auto *actionBox = addComboRow(layout, "Action", armActions);
                SliderField angleField = createU16Field("Angle", 120, layout);
                auto *overrideEdit = addOverrideRow(layout, "arm-relative left 40 up 120");
                auto buildCommand = [this, partBox, speedField, actionBox, angleField, overrideEdit]() {
                    auto overrideText = overrideEdit->text().trimmed();
                    if (!overrideText.isEmpty()) {
                        return overrideText;
                    }
                    return QString("arm-relative %1 %2 %3 %4")
                        .arg(comboValue(partBox), valueFromField(speedField),
                             comboValue(actionBox), valueFromField(angleField));
                };
                return CommandWidgets{panel, buildCommand};
            }
        });

        commands.push_back(CommandDefinition{
            "Arm absolute",
            {"Locomotion", "Arms"},
            "arm-absolute",
            [this, armParts]() {
                auto *panel = new QWidget;
                auto *layout = new QVBoxLayout(panel);
                auto *partBox = addComboRow(layout, "Part", armParts);
                SliderField speedField = createByteField("Speed", 40, layout);
                SliderField angleField = createU16Field("Angle", 120, layout);
                auto *overrideEdit = addOverrideRow(layout, "arm-absolute left 40 120");
                auto buildCommand = [this, partBox, speedField, angleField, overrideEdit]() {
                    auto overrideText = overrideEdit->text().trimmed();
                    if (!overrideText.isEmpty()) {
                        return overrideText;
                    }
                    return QString("arm-absolute %1 %2 %3")
                        .arg(comboValue(partBox), valueFromField(speedField), valueFromField(angleField));
                };
                return CommandWidgets{panel, buildCommand};
            }
        });

        commands.push_back(CommandDefinition{
            "Head no-angle",
            {"Locomotion", "Head"},
            "head-no-angle",
            [this, headActions]() {
                auto *panel = new QWidget;
                auto *layout = new QVBoxLayout(panel);
                auto *actionBox = addComboRow(layout, "Action", headActions);
                SliderField speedField = createByteField("Speed", 40, layout);
                auto *overrideEdit = addOverrideRow(layout, "head-no-angle up 40");
                auto buildCommand = [this, actionBox, speedField, overrideEdit]() {
                    auto overrideText = overrideEdit->text().trimmed();
                    if (!overrideText.isEmpty()) {
                        return overrideText;
                    }
                    return QString("head-no-angle %1 %2")
                        .arg(comboValue(actionBox), valueFromField(speedField));
                };
                return CommandWidgets{panel, buildCommand};
            }
        });

        commands.push_back(CommandDefinition{
            "Head relative",
            {"Locomotion", "Head"},
            "head-relative",
            [this, headActions]() {
                auto *panel = new QWidget;
                auto *layout = new QVBoxLayout(panel);
                auto *actionBox = addComboRow(layout, "Action", headActions);
                SliderField angleField = createU16Field("Angle (ignored for reset actions)", 20, layout);
                auto *overrideEdit = addOverrideRow(layout, "head-relative left 20");
                auto buildCommand = [this, actionBox, angleField, overrideEdit]() {
                    auto overrideText = overrideEdit->text().trimmed();
                    if (!overrideText.isEmpty()) {
                        return overrideText;
                    }
                    auto action = comboValue(actionBox);
                    if (action == "vertical-reset" || action == "horizontal-reset" || action == "centre-reset") {
                        return QString("head-relative %1").arg(action);
                    }
                    return QString("head-relative %1 %2")
                        .arg(action, valueFromField(angleField));
                };
                return CommandWidgets{panel, buildCommand};
            }
        });

        commands.push_back(CommandDefinition{
            "Head absolute",
            {"Locomotion", "Head"},
            "head-absolute",
            [this, headAbsActions]() {
                auto *panel = new QWidget;
                auto *layout = new QVBoxLayout(panel);
                auto *actionBox = addComboRow(layout, "Action", headAbsActions);
                SliderField angleField = createU16Field("Angle", 15, layout);
                auto *overrideEdit = addOverrideRow(layout, "head-absolute vertical 15");
                auto buildCommand = [this, actionBox, angleField, overrideEdit]() {
                    auto overrideText = overrideEdit->text().trimmed();
                    if (!overrideText.isEmpty()) {
                        return overrideText;
                    }
                    return QString("head-absolute %1 %2")
                        .arg(comboValue(actionBox), valueFromField(angleField));
                };
                return CommandWidgets{panel, buildCommand};
            }
        });

        commands.push_back(CommandDefinition{
            "Head locate absolute",
            {"Locomotion", "Head"},
            "head-locate-absolute",
            [this, headLockActions]() {
                auto *panel = new QWidget;
                auto *layout = new QVBoxLayout(panel);
                auto *actionBox = addComboRow(layout, "Lock", headLockActions);
                SliderField hAngleField = createU16Field("Horizontal angle", 30, layout);
                SliderField vAngleField = createU16Field("Vertical angle", 20, layout);
                auto *overrideEdit = addOverrideRow(layout, "head-locate-absolute both-lock 30 20");
                auto buildCommand = [this, actionBox, hAngleField, vAngleField, overrideEdit]() {
                    auto overrideText = overrideEdit->text().trimmed();
                    if (!overrideText.isEmpty()) {
                        return overrideText;
                    }
                    return QString("head-locate-absolute %1 %2 %3")
                        .arg(comboValue(actionBox), valueFromField(hAngleField), valueFromField(vAngleField));
                };
                return CommandWidgets{panel, buildCommand};
            }
        });

        commands.push_back(CommandDefinition{
            "Head locate relative",
            {"Locomotion", "Head"},
            "head-locate-relative",
            [this, headLockActions, headHorizontalDirections, headVerticalDirections]() {
                auto *panel = new QWidget;
                auto *layout = new QVBoxLayout(panel);
                auto *lockBox = addComboRow(layout, "Lock", headLockActions);
                SliderField hAngleField = createByteField("Horizontal angle", 10, layout);
                SliderField vAngleField = createByteField("Vertical angle", 10, layout);
                auto *hDirBox = addComboRow(layout, "Horizontal direction", headHorizontalDirections);
                auto *vDirBox = addComboRow(layout, "Vertical direction", headVerticalDirections);
                auto *overrideEdit = addOverrideRow(layout, "head-locate-relative both-lock 10 10 left up");
                auto buildCommand = [this, lockBox, hAngleField, vAngleField, hDirBox, vDirBox, overrideEdit]() {
                    auto overrideText = overrideEdit->text().trimmed();
                    if (!overrideText.isEmpty()) {
                        return overrideText;
                    }
                    return QString("head-locate-relative %1 %2 %3 %4 %5")
                        .arg(comboValue(lockBox), valueFromField(hAngleField), valueFromField(vAngleField),
                             comboValue(hDirBox), comboValue(vDirBox));
                };
                return CommandWidgets{panel, buildCommand};
            }
        });

        commands.push_back(CommandDefinition{
            "Head centre",
            {"Locomotion", "Head"},
            "head-centre",
            [this]() {
                auto *panel = new QWidget;
                auto *layout = new QVBoxLayout(panel);
                layout->addWidget(new QLabel("Centers the head with lock."));
                auto *overrideEdit = addOverrideRow(layout, "head-centre");
                auto buildCommand = [overrideEdit]() {
                    auto overrideText = overrideEdit->text().trimmed();
                    if (!overrideText.isEmpty()) {
                        return overrideText;
                    }
                    return QString("head-centre");
                };
                return CommandWidgets{panel, buildCommand};
            }
        });
    }

    void rebuildTree() {
        commandTree->clear();
        commandIndex.clear();

        for (size_t i = 0; i < commands.size(); ++i) {
            auto &command = commands[i];
            QTreeWidgetItem *parent = nullptr;
            for (const auto &category : command.categories) {
                parent = ensureCategory(parent, category);
            }
            QTreeWidgetItem *item = nullptr;
            if (parent) {
                item = new QTreeWidgetItem(parent, QStringList{command.name});
            } else {
                item = new QTreeWidgetItem(commandTree, QStringList{command.name});
            }
            commandIndex[item] = static_cast<int>(i);
        }
        commandTree->expandAll();
    }

    QTreeWidgetItem *ensureCategory(QTreeWidgetItem *parent, const QString &name) {
        int count = parent ? parent->childCount() : commandTree->topLevelItemCount();
        for (int i = 0; i < count; ++i) {
            auto *child = parent ? parent->child(i) : commandTree->topLevelItem(i);
            if (child->text(0) == name && commandIndex.find(child) == commandIndex.end()) {
                return child;
            }
        }
        if (parent) {
            return new QTreeWidgetItem(parent, QStringList{name});
        }
        return new QTreeWidgetItem(commandTree, QStringList{name});
    }

    void applyFilter(const QString &text) {
        auto trimmed = text.trimmed();
        for (int i = 0; i < commandTree->topLevelItemCount(); ++i) {
            auto *item = commandTree->topLevelItem(i);
            filterItem(item, trimmed);
        }
    }

    bool filterItem(QTreeWidgetItem *item, const QString &text) {
        bool matches = item->text(0).contains(text, Qt::CaseInsensitive);
        bool childMatches = false;
        for (int i = 0; i < item->childCount(); ++i) {
            childMatches = filterItem(item->child(i), text) || childMatches;
        }
        bool visible = text.isEmpty() || matches || childMatches;
        item->setHidden(!visible);
        return matches || childMatches;
    }

    void cleanupActivePanel() {
        if (activeWidgets.panel) {
            commandStack->removeWidget(activeWidgets.panel);
            delete activeWidgets.panel;
            activeWidgets.panel = nullptr;
        }
    }

    void selectCommand() {
        auto items = commandTree->selectedItems();
        if (items.isEmpty()) {
            commandStack->setCurrentIndex(0);
            cleanupActivePanel();
            activeWidgets = CommandWidgets{};
            return;
        }
        auto *item = items.first();
        auto it = commandIndex.find(item);
        if (it == commandIndex.end()) {
            commandStack->setCurrentIndex(0);
            cleanupActivePanel();
            activeWidgets = CommandWidgets{};
            return;
        }
        auto &definition = commands[it->second];
        
        // Remove old widget to prevent memory leak
        cleanupActivePanel();
        
        activeWidgets = definition.builder();
        commandStack->addWidget(activeWidgets.panel);
        commandStack->setCurrentWidget(activeWidgets.panel);
    }

    void sendSelectedCommand() {
        if (!activeWidgets.panel) {
            return;
        }
        auto command = activeWidgets.buildCommand();
        if (command.isEmpty()) {
            return;
        }
        runCommand(command);
    }

    void sendHexCommand() {
        auto text = hexInput->text().trimmed();
        if (text.isEmpty()) {
            return;
        }
        runCommand(QString("hex-send %1").arg(text));
    }

    static QString valueFromField(const SliderField &field) {
        auto overrideText = field.overrideEdit->text().trimmed();
        if (!overrideText.isEmpty()) {
            return overrideText;
        }
        return QString::number(field.spin->value());
    }

    SliderField createSliderField(const QString &label, int min, int max, int value, QVBoxLayout *layout) {
        auto *row = new QHBoxLayout;
        row->addWidget(new QLabel(label));

        auto *slider = new QSlider(Qt::Horizontal);
        slider->setRange(min, max);
        slider->setValue(value);

        auto *spin = new QSpinBox;
        spin->setRange(min, max);
        spin->setValue(value);

        auto *overrideEdit = new QLineEdit;
        overrideEdit->setPlaceholderText("Override");

        row->addWidget(slider);
        row->addWidget(spin);
        row->addWidget(overrideEdit);

        layout->addLayout(row);

        connect(slider, &QSlider::valueChanged, spin, &QSpinBox::setValue);
        connect(spin, QOverload<int>::of(&QSpinBox::valueChanged), slider, &QSlider::setValue);

        return SliderField{slider, spin, overrideEdit};
    }

    SliderField createByteField(const QString &label, int value, QVBoxLayout *layout) {
        return createSliderField(label, 0, 255, value, layout);
    }

    SliderField createU16Field(const QString &label, int value, QVBoxLayout *layout) {
        return createSliderField(label, 0, 65535, value, layout);
    }

    QComboBox *addComboRow(QVBoxLayout *layout, const QString &label,
                           const QVector<QPair<QString, QString>> &items) {
        auto *row = new QHBoxLayout;
        row->addWidget(new QLabel(label));
        auto *box = new QComboBox;
        for (const auto &item : items) {
            box->addItem(item.first, item.second);
        }
        row->addWidget(box);
        layout->addLayout(row);
        return box;
    }

    QString comboValue(QComboBox *box) {
        auto data = box->currentData();
        if (data.isValid()) {
            return data.toString();
        }
        return box->currentText().toLower();
    }

    QLineEdit *addOverrideRow(QVBoxLayout *layout, const QString &placeholder) {
        auto *overrideRow = new QHBoxLayout;
        overrideRow->addWidget(new QLabel("Command override"));
        auto *overrideEdit = new QLineEdit;
        overrideEdit->setPlaceholderText(placeholder);
        overrideRow->addWidget(overrideEdit);
        layout->addLayout(overrideRow);
        return overrideEdit;
    }

    QWidget *buildExecutionPanel() {
        auto *box = new QGroupBox("Execution options");
        auto *layout = new QVBoxLayout(box);
        verboseEnabled = new QCheckBox("Verbose (show bytes)");
        testEnabled = new QCheckBox("Test mode (no USB send)");
        layout->addWidget(verboseEnabled);
        layout->addWidget(testEnabled);
        return box;
    }

    QWidget *buildSshPanel() {
        auto *box = new QGroupBox("Remote Raspberry Pi");
        auto *layout = new QVBoxLayout(box);

        sshEnabled = new QCheckBox("Run commands over SSH");
        layout->addWidget(sshEnabled);

        auto *hostRow = new QHBoxLayout;
        hostRow->addWidget(new QLabel("Host"));
        sshHost = new QLineEdit;
        sshHost->setPlaceholderText("raspberrypi.local");
        hostRow->addWidget(sshHost);
        layout->addLayout(hostRow);

        auto *userRow = new QHBoxLayout;
        userRow->addWidget(new QLabel("User"));
        sshUser = new QLineEdit;
        sshUser->setPlaceholderText("pi");
        userRow->addWidget(sshUser);
        layout->addLayout(userRow);

        auto *dirRow = new QHBoxLayout;
        dirRow->addWidget(new QLabel("Project directory"));
        sshDirectory = new QLineEdit;
        sshDirectory->setPlaceholderText("~/Sanbot-MCU-Bridge");
        dirRow->addWidget(sshDirectory);
        layout->addLayout(dirRow);

        openTerminal = new QPushButton("Open SSH terminal");
        layout->addWidget(openTerminal);

        return box;
    }

    QString logDirectory() const {
        QString base = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
        if (base.isEmpty()) {
            base = QDir::homePath() + "/.sanbot-mcu-bridge";
        }
        QDir baseDir(base);
        baseDir.mkpath(".");
        QString logsPath = baseDir.filePath("logs");
        QDir logsDir(logsPath);
        logsDir.mkpath(".");
        return logsPath;
    }

    QString createLogPath() const {
        QDir logsDir(logDirectory());
        QString name = QDateTime::currentDateTime().toString("yyyy-MM-dd_HH-mm-ss-zzz") + ".log";
        return logsDir.filePath(name);
    }

    void appendLogLine(const QString &logPath, const QString &line) const {
        if (logPath.isEmpty()) {
            return;
        }
        QFile file(logPath);
        if (!file.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text)) {
            return;
        }
        QTextStream out(&file);
        auto stamp = QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss");
        out << "[" << stamp << "] " << line << "\n";
    }

    void appendOutput(const QString &logPath, const QString &line) {
        if (line.isEmpty()) {
            return;
        }
        outputLog->append(line);
        appendLogLine(logPath, line);
    }

    QString shellQuote(const QString &value) const {
        QString escaped = value;
        escaped.replace("'", "'\"'\"'");
        return "'" + escaped + "'";
    }

    QString resolveLocalCliPath() const {
        QString appDir = QCoreApplication::applicationDirPath();
        QStringList candidates = {
            QDir(appDir).filePath("sanbot-mcu-bridge"),
            QDir(appDir).filePath("../sanbot-mcu-bridge"),
            QDir::current().filePath("sanbot-mcu-bridge"),
            QDir::current().filePath("core/build-mac/sanbot-mcu-bridge")
        };
        for (const auto &path : candidates) {
            QFileInfo info(path);
            if (info.exists() && info.isFile() && info.isExecutable()) {
                return info.absoluteFilePath();
            }
        }
        return {};
    }

    QStringList buildCliArguments(const QString &command) const {
        QStringList args;
        if (verboseEnabled && verboseEnabled->isChecked()) {
            args << "--verbose";
        }
        if (testEnabled && testEnabled->isChecked()) {
            args << "--test";
        }
        args.append(QProcess::splitCommand(command));
        return args;
    }

    void runCommand(const QString &command) {
        auto trimmed = command.trimmed();
        if (trimmed.isEmpty()) {
            return;
        }

        QString logPath = createLogPath();
        appendOutput(logPath, QString("Command: %1").arg(trimmed));
        appendOutput(logPath, QString("Log file: %1").arg(logPath));

        auto *process = new QProcess(this);
        auto args = buildCliArguments(trimmed);

        connect(process, &QProcess::readyReadStandardOutput, this, [this, process, logPath]() {
            auto text = QString::fromUtf8(process->readAllStandardOutput());
            for (const auto &line : text.split('\n', Qt::SkipEmptyParts)) {
                appendOutput(logPath, line);
            }
        });
        connect(process, &QProcess::readyReadStandardError, this, [this, process, logPath]() {
            auto text = QString::fromUtf8(process->readAllStandardError());
            for (const auto &line : text.split('\n', Qt::SkipEmptyParts)) {
                appendOutput(logPath, line);
            }
        });
        connect(process, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished), this,
                [this, process, logPath](int code, QProcess::ExitStatus) {
                    appendOutput(logPath, QString("Finished with code %1").arg(code));
                    process->deleteLater();
                });
        connect(process, &QProcess::errorOccurred, this, [this, process, logPath](QProcess::ProcessError) {
            appendOutput(logPath, QString("Process error: %1").arg(process->errorString()));
        });

        if (sshEnabled->isChecked()) {
            auto host = sshHost->text().trimmed();
            auto user = sshUser->text().trimmed();
            auto directory = sshDirectory->text().trimmed();
            if (host.isEmpty() || user.isEmpty() || directory.isEmpty()) {
                appendOutput(logPath, "SSH settings are incomplete");
                process->deleteLater();
                return;
            }
            auto sshTarget = QString("%1@%2").arg(user, host);
            QStringList quotedArgs;
            for (const auto &arg : args) {
                quotedArgs << shellQuote(arg);
            }
            auto remoteCommand = QString("cd %1 && %2 %3")
                                     .arg(shellQuote(directory),
                                          shellQuote("./sanbot-mcu-bridge"),
                                          quotedArgs.join(' '));
            appendOutput(logPath, QString("SSH: ssh %1 %2").arg(sshTarget, remoteCommand));
            process->start("ssh", {sshTarget, remoteCommand});
            return;
        }

        appendOutput(logPath, "Local mode enabled");
        auto localCli = resolveLocalCliPath();
        if (localCli.isEmpty()) {
            appendOutput(logPath, "Local CLI not found. Build sanbot-mcu-bridge or set SSH mode.");
            process->deleteLater();
            return;
        }
        appendOutput(logPath, QString("Local CLI: %1").arg(localCli));
        process->setWorkingDirectory(QFileInfo(localCli).absolutePath());
        process->start(localCli, args);
    }

    void launchTerminal() {
        auto host = sshHost->text().trimmed();
        auto user = sshUser->text().trimmed();
        auto directory = sshDirectory->text().trimmed();
        if (host.isEmpty() || user.isEmpty() || directory.isEmpty()) {
            outputLog->append("SSH settings are incomplete");
            return;
        }
        auto sshTarget = QString("%1@%2").arg(user, host);
        auto command = QString("ssh %1 -t \"cd %2 && exec \\$SHELL -l\"").arg(sshTarget, directory);
        outputLog->append(QString("Terminal: %1").arg(command));

        auto platform = QSysInfo::productType();
        if (platform == "osx") {
            QProcess::startDetached("open", {"-a", "Terminal", command});
            return;
        }
        if (platform == "windows") {
            QProcess::startDetached("cmd", {"/K", command});
            return;
        }
        QProcess::startDetached("x-terminal-emulator", {"-e", command});
    }
};

int main(int argc, char **argv) {
    QApplication app(argc, argv);
    MainWindow window;
    window.resize(1100, 700);
    window.show();
    return app.exec();
}
