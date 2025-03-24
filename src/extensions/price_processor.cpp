// src/extensions/price_processor.cpp
#include <Python.h>
#include <unordered_map>
#include <string>
#include <vector>
#include <cmath>

/**
 * High-performance price processing engine for handling ticks
 * and identifying potential price triggers
 */
class PriceProcessor {
private:
    std::unordered_map<std::string, double> last_prices;
    std::unordered_map<std::string, std::string> trade_types;
    std::unordered_map<std::string, double> target_prices;
    std::unordered_map<std::string, double> trigger_prices;
    std::unordered_map<std::string, double> gtt_prices;
    double trigger_threshold;

public:
    PriceProcessor() : trigger_threshold(0.99) {}

    void set_trigger_threshold(double threshold) {
        trigger_threshold = threshold;
    }

    void update_price(const std::string& symbol, double price) {
        last_prices[symbol] = price;
    }

    void update_prices(const std::vector<std::string>& symbols, 
                      const std::vector<double>& prices) {
        for (size_t i = 0; i < symbols.size() && i < prices.size(); ++i) {
            last_prices[symbols[i]] = prices[i];
        }
    }

    void set_symbol_data(const std::string& symbol, 
                         const std::string& trade_type,
                         double target_price,
                         double trigger_price,
                         double gtt_price) {
        trade_types[symbol] = trade_type;
        target_prices[symbol] = target_price;
        trigger_prices[symbol] = trigger_price;
        gtt_prices[symbol] = gtt_price;
    }

    std::vector<std::pair<std::string, double>> find_potential_triggers() {
        std::vector<std::pair<std::string, double>> candidates;

        for (const auto& [symbol, price] : last_prices) {
            // Skip symbols without required data
            if (!trade_types.count(symbol) || !gtt_prices.count(symbol)) {
                continue;
            }

            const auto& trade_type = trade_types[symbol];
            const auto& gtt_price = gtt_prices[symbol];

            // Check if price is close to trigger based on trade type
            if (trade_type == "SHORT" && price >= gtt_price * trigger_threshold) {
                candidates.emplace_back(symbol, price);
            } else if (trade_type == "LONG" && price <= gtt_price / trigger_threshold) {
                candidates.emplace_back(symbol, price);
            }
        }

        return candidates;
    }

    std::vector<std::pair<std::string, double>> check_triggers() {
        std::vector<std::pair<std::string, double>> triggered;

        for (const auto& [symbol, price] : last_prices) {
            // Skip symbols without required data
            if (!trade_types.count(symbol) || !gtt_prices.count(symbol)) {
                continue;
            }

            const auto& trade_type = trade_types[symbol];
            const auto& gtt_price = gtt_prices[symbol];

            // Check if trigger condition is met
            if (trade_type == "SHORT" && price >= gtt_price) {
                triggered.emplace_back(symbol, price);
            } else if (trade_type == "LONG" && price <= gtt_price) {
                triggered.emplace_back(symbol, price);
            }
        }

        return triggered;
    }
};

// Singleton instance for the processor
static PriceProcessor* processor = nullptr;

// Python module functions

static PyObject* init_processor(PyObject* self, PyObject* args) {
    if (processor == nullptr) {
        processor = new PriceProcessor();
    }
    Py_RETURN_NONE;
}

static PyObject* set_trigger_threshold(PyObject* self, PyObject* args) {
    double threshold;
    if (!PyArg_ParseTuple(args, "d", &threshold)) {
        return NULL;
    }

    if (processor == nullptr) {
        processor = new PriceProcessor();
    }
    processor->set_trigger_threshold(threshold);
    Py_RETURN_NONE;
}

static PyObject* update_price(PyObject* self, PyObject* args) {
    const char* symbol;
    double price;
    if (!PyArg_ParseTuple(args, "sd", &symbol, &price)) {
        return NULL;
    }

    if (processor == nullptr) {
        processor = new PriceProcessor();
    }
    processor->update_price(symbol, price);
    Py_RETURN_NONE;
}

static PyObject* update_prices(PyObject* self, PyObject* args) {
    PyObject* symbols_list;
    PyObject* prices_list;
    if (!PyArg_ParseTuple(args, "OO", &symbols_list, &prices_list)) {
        return NULL;
    }

    if (!PyList_Check(symbols_list) || !PyList_Check(prices_list)) {
        PyErr_SetString(PyExc_TypeError, "Arguments must be lists");
        return NULL;
    }

    if (processor == nullptr) {
        processor = new PriceProcessor();
    }

    // Convert Python lists to C++ vectors
    std::vector<std::string> symbols;
    std::vector<double> prices;

    Py_ssize_t symbols_size = PyList_Size(symbols_list);
    Py_ssize_t prices_size = PyList_Size(prices_list);
    Py_ssize_t min_size = symbols_size < prices_size ? symbols_size : prices_size;

    for (Py_ssize_t i = 0; i < min_size; ++i) {
        PyObject* symbol_obj = PyList_GetItem(symbols_list, i);
        PyObject* price_obj = PyList_GetItem(prices_list, i);

        if (!PyUnicode_Check(symbol_obj) || !PyFloat_Check(price_obj)) {
            continue;
        }

        const char* symbol = PyUnicode_AsUTF8(symbol_obj);
        double price = PyFloat_AsDouble(price_obj);
        
        symbols.push_back(symbol);
        prices.push_back(price);
    }

    processor->update_prices(symbols, prices);
    Py_RETURN_NONE;
}

static PyObject* set_symbol_data(PyObject* self, PyObject* args) {
    const char* symbol;
    const char* trade_type;
    double target_price, trigger_price, gtt_price;
    
    if (!PyArg_ParseTuple(args, "ssddd", &symbol, &trade_type, &target_price, 
                          &trigger_price, &gtt_price)) {
        return NULL;
    }

    if (processor == nullptr) {
        processor = new PriceProcessor();
    }
    
    processor->set_symbol_data(symbol, trade_type, target_price, trigger_price, gtt_price);
    Py_RETURN_NONE;
}

static PyObject* find_potential_triggers(PyObject* self, PyObject* args) {
    if (processor == nullptr) {
        processor = new PriceProcessor();
    }
    
    auto candidates = processor->find_potential_triggers();
    
    // Create Python list of results
    PyObject* result = PyList_New(candidates.size());
    for (size_t i = 0; i < candidates.size(); ++i) {
        PyObject* tuple = PyTuple_New(2);
        PyTuple_SetItem(tuple, 0, PyUnicode_FromString(candidates[i].first.c_str()));
        PyTuple_SetItem(tuple, 1, PyFloat_FromDouble(candidates[i].second));
        PyList_SetItem(result, i, tuple);
    }
    
    return result;
}

static PyObject* check_triggers(PyObject* self, PyObject* args) {
    if (processor == nullptr) {
        processor = new PriceProcessor();
    }
    
    auto triggered = processor->check_triggers();
    
    // Create Python list of results
    PyObject* result = PyList_New(triggered.size());
    for (size_t i = 0; i < triggered.size(); ++i) {
        PyObject* tuple = PyTuple_New(2);
        PyTuple_SetItem(tuple, 0, PyUnicode_FromString(triggered[i].first.c_str()));
        PyTuple_SetItem(tuple, 1, PyFloat_FromDouble(triggered[i].second));
        PyList_SetItem(result, i, tuple);
    }
    
    return result;
}

static PyObject* cleanup(PyObject* self, PyObject* args) {
    delete processor;
    processor = nullptr;
    Py_RETURN_NONE;
}

// Module method table
static PyMethodDef PriceProcessorMethods[] = {
    {"init_processor", init_processor, METH_NOARGS, "Initialize the price processor"},
    {"set_trigger_threshold", set_trigger_threshold, METH_VARARGS, "Set the trigger threshold percentage"},
    {"update_price", update_price, METH_VARARGS, "Update price for a symbol"},
    {"update_prices", update_prices, METH_VARARGS, "Update prices for multiple symbols"},
    {"set_symbol_data", set_symbol_data, METH_VARARGS, "Set symbol trading data"},
    {"find_potential_triggers", find_potential_triggers, METH_NOARGS, "Find symbols close to triggering"},
    {"check_triggers", check_triggers, METH_NOARGS, "Check for triggered symbols"},
    {"cleanup", cleanup, METH_NOARGS, "Clean up resources"},
    {NULL, NULL, 0, NULL}  // Sentinel
};

// Module definition
static struct PyModuleDef price_processor_module = {
    PyModuleDef_HEAD_INIT,
    "price_processor",
    "High-performance price processing engine",
    -1,
    PriceProcessorMethods
};

// Module initialization function
PyMODINIT_FUNC PyInit_price_processor(void) {
    return PyModule_Create(&price_processor_module);
}